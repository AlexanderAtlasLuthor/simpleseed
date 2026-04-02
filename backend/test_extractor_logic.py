"""
Minimal test for extractor chunking + merge logic.
Does NOT call the LLM — only exercises pure-Python functions.
"""
import sys
sys.path.insert(0, ".")
import services.extractor as ext

# ── Case 1: short doc stays in single-pass path ─────────────────────────────
short = "RFP cloud services budget 500k deadline April. " * 30  # ~1,400 chars
assert len(short) < ext._SINGLE_PASS_LIMIT
print(f"Case 1 PASS: {len(short):,} chars < limit {ext._SINGLE_PASS_LIMIT:,} → single-pass")

# ── Case 2: chunking with tiny chunk size ────────────────────────────────────
# Use a reduced chunk size so we can test splitting without large strings
ext._CHUNK_SIZE = 150

text = (
    "CLIENT: DeptTech. DEADLINE: April 30.\n"   # chars 0-38
    + "pad " * 30                                # ~120 chars filler
    + "REQ-MID: real-time pipeline.\n"           # char ~158
    + "pad " * 30                                # ~120 chars filler
    + "EVAL-END: technical merit 40%.\n"         # char ~318
)

pos_mid = text.find("REQ-MID")
pos_end = text.find("EVAL-END")
old_limit = 50
assert pos_mid > old_limit, "REQ-MID should be past old 8k-equivalent limit"
assert pos_end > old_limit, "EVAL-END should be past old 8k-equivalent limit"

chunks = ext._split_into_chunks(text)
req_found  = any("REQ-MID"  in c for c in chunks)
eval_found = any("EVAL-END" in c for c in chunks)
assert req_found,  "REQ-MID not found in any chunk"
assert eval_found, "EVAL-END not found in any chunk"
print(f"Case 2 PASS: {len(chunks)} chunks cover REQ-MID={req_found} EVAL-END={eval_found}")

# ── Case 3: merge captures info from all chunk partials ──────────────────────
partials = [
    {"summary": "Agency seeks cloud vendor.", "client": "DeptTech",
     "deadline": "April 30, 2025", "budget": "$750,000",
     "requirements": ["Intro req"],
     "evaluation_criteria": [], "deliverables": [], "keywords": ["cloud"]},
    {"summary": "", "client": None, "deadline": None, "budget": None,
     "requirements": ["REQ-MID-1: real-time pipeline", "REQ-MID-2: OAuth 2.0"],
     "evaluation_criteria": [], "deliverables": [], "keywords": ["pipeline"]},
    {"summary": "", "client": None, "deadline": None, "budget": None,
     "requirements": [],
     "evaluation_criteria": ["EVAL-END-1: Technical merit 40%"],
     "deliverables": ["DEL-END-1: Final report", "DEL-END-3: 90-day support"],
     "keywords": ["evaluation"]},
]

m = ext._merge_extractions(partials)
assert m["client"]   == "DeptTech",        f"client wrong: {m['client']}"
assert m["deadline"] == "April 30, 2025",  f"deadline wrong: {m['deadline']}"
assert m["budget"]   == "$750,000",        f"budget wrong: {m['budget']}"
assert any("REQ-MID-1" in r for r in m["requirements"]),        "REQ-MID-1 lost in merge"
assert any("EVAL-END-1" in c for c in m["evaluation_criteria"]), "EVAL-END-1 lost in merge"
assert any("DEL-END-3" in d for d in m["deliverables"]),         "DEL-END-3 lost in merge"
print(f"Case 3 PASS: merge captured {len(m['requirements'])} req, "
      f"{len(m['evaluation_criteria'])} criteria, {len(m['deliverables'])} deliverables")
print(f"  client={m['client']}  deadline={m['deadline']}  budget={m['budget']}")
print(f"  requirements   : {m['requirements']}")
print(f"  eval_criteria  : {m['evaluation_criteria']}")
print(f"  deliverables   : {m['deliverables']}")

# ── Case 4: deduplication ────────────────────────────────────────────────────
dupe = [
    {"summary":"s","client":None,"deadline":None,"budget":None,
     "requirements":["REST API","99.9% uptime"],"evaluation_criteria":[],
     "deliverables":[],"keywords":[]},
    {"summary":"s","client":None,"deadline":None,"budget":None,
     "requirements":["REST API","OAuth 2.0"],   # REST API is a duplicate
     "evaluation_criteria":[],"deliverables":[],"keywords":[]},
]
md = ext._merge_extractions(dupe)
assert len(md["requirements"]) == 3, f"Expected 3 unique items, got {len(md['requirements'])}"
print(f"Case 4 PASS: 'REST API' in 2 chunks → deduplicated. Final: {md['requirements']}")

print("\nAll cases passed.")
