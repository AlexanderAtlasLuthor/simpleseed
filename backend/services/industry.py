"""
Single source of truth for supported industries.

Each industry carries a context descriptor used by generator.py and scoring.py
to adapt their LLM prompts. Adding a new industry means adding one entry here —
nothing else needs to change.
"""
from typing import Optional

# All recognized industry identifiers (canonical lowercase).
SUPPORTED_INDUSTRIES = {
    "technology",
    "consulting",
    "healthcare",
    "construction",
    "government_contracting",
    "education",
    "general",
}

# Used when no industry is specified or the value is unrecognized.
DEFAULT_INDUSTRY = "general"

# Per-industry context descriptors consumed by LLM prompt builders.
INDUSTRY_CONTEXT: dict[str, dict] = {
    "technology": {
        "label": "Technology",
        "vendor_type": "technology company or software development firm",
        "focus": (
            "software architecture, cloud infrastructure, APIs and integrations, "
            "cybersecurity, data engineering, DevOps practices, and technical delivery"
        ),
        "tone": "technical and precise",
        "relevant_domains": [
            "software development", "cloud platforms", "API design",
            "data engineering", "cybersecurity", "infrastructure", "system integration",
        ],
    },
    "consulting": {
        "label": "Consulting",
        "vendor_type": "management or strategy consulting firm",
        "focus": (
            "advisory services, process improvement, organizational change management, "
            "stakeholder engagement, performance analysis, and strategic recommendations"
        ),
        "tone": "professional and advisory",
        "relevant_domains": [
            "strategy", "change management", "process optimization",
            "stakeholder management", "performance measurement", "organizational design",
        ],
    },
    "healthcare": {
        "label": "Healthcare",
        "vendor_type": "healthcare services or health IT vendor",
        "focus": (
            "clinical workflows, patient outcomes, HIPAA and regulatory compliance, "
            "EHR/EMR integration, care coordination, health data privacy, "
            "and clinical operations"
        ),
        "tone": "clinical and compliance-focused",
        "relevant_domains": [
            "clinical operations", "patient safety", "HIPAA compliance",
            "EHR integration", "care coordination", "health informatics",
            "regulatory requirements",
        ],
    },
    "construction": {
        "label": "Construction",
        "vendor_type": "general contractor or construction management firm",
        "focus": (
            "project delivery, subcontractor coordination, site safety and OSHA compliance, "
            "permitting and inspections, quality control, schedule management, "
            "and cost estimation"
        ),
        "tone": "practical and delivery-focused",
        "relevant_domains": [
            "project management", "subcontractor coordination", "site safety",
            "OSHA compliance", "scheduling", "cost control", "permitting",
            "quality assurance",
        ],
    },
    "government_contracting": {
        "label": "Government Contracting",
        "vendor_type": "government contractor or federal services firm",
        "focus": (
            "FAR/DFARS compliance, contract vehicles (GSA, SEWP, CIO-SP3), "
            "security clearances, past performance documentation, "
            "agency mission alignment, and federal procurement requirements"
        ),
        "tone": "formal and compliance-oriented",
        "relevant_domains": [
            "FAR compliance", "contract vehicles", "security clearances",
            "past performance", "federal procurement", "DFARS", "CMMC",
            "agency requirements",
        ],
    },
    "education": {
        "label": "Education",
        "vendor_type": "educational services or ed-tech vendor",
        "focus": (
            "curriculum design, learning outcomes, FERPA and student data privacy, "
            "student engagement, institutional requirements, accreditation standards, "
            "and faculty or staff training"
        ),
        "tone": "collaborative and outcomes-focused",
        "relevant_domains": [
            "curriculum development", "learning outcomes", "FERPA compliance",
            "accreditation", "student engagement", "institutional partnerships",
        ],
    },
    "general": {
        "label": "General",
        "vendor_type": "professional services vendor",
        "focus": (
            "delivering value, meeting stated requirements, demonstrating relevant "
            "experience, and providing a clear and credible approach"
        ),
        "tone": "professional and neutral",
        "relevant_domains": [],
    },
}


def resolve_industry(industry: Optional[str]) -> str:
    """
    Normalize and validate an industry string.
    Returns DEFAULT_INDUSTRY if the value is None, empty, or unrecognized.
    Never raises — always returns a valid key.
    """
    if not industry:
        return DEFAULT_INDUSTRY
    normalized = industry.lower().strip()
    return normalized if normalized in SUPPORTED_INDUSTRIES else DEFAULT_INDUSTRY


def get_industry_context(industry: Optional[str]) -> dict:
    """Return the context descriptor for a given industry key."""
    return INDUSTRY_CONTEXT[resolve_industry(industry)]
