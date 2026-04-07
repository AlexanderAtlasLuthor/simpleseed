"use client";
import { useEffect, useState } from "react";

interface Profile {
  company_name: string;
  industries: string[];
  capabilities: string[];
  services: string[];
  certifications: string[];
  geographies: string[];
  past_performance_keywords: string[];
  preferred_project_types: string[];
  excluded_project_types: string[];
  capacity_constraints: string[];
  target_contract_size: { min?: number; max?: number };
}

const EMPTY: Profile = {
  company_name: "",
  industries: [],
  capabilities: [],
  services: [],
  certifications: [],
  geographies: [],
  past_performance_keywords: [],
  preferred_project_types: [],
  excluded_project_types: [],
  capacity_constraints: [],
  target_contract_size: {},
};

function TagInput({
  label,
  hint,
  values,
  onChange,
}: {
  label: string;
  hint?: string;
  values: string[];
  onChange: (v: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const v = draft.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setDraft("");
  };

  const remove = (idx: number) => onChange(values.filter((_, i) => i !== idx));

  return (
    <div>
      <label className="block text-xs text-[#6b8f72] mb-1.5">{label}</label>
      {hint && <p className="text-xs text-[#3d5c44] mb-2">{hint}</p>}
      <div className="flex gap-2 mb-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
          placeholder="Type and press Enter"
          className="flex-1 bg-[#0d1610] border border-[#1e2d22] rounded-xl px-4 py-2.5 text-sm text-[#e8f5eb] placeholder-[#3d5c44] focus:outline-none focus:border-seed-700 transition-colors"
        />
        <button
          type="button"
          onClick={add}
          className="px-4 py-2.5 rounded-xl border border-[#1e2d22] bg-[#0d1610] text-seed-400 text-sm hover:border-seed-800 transition-colors"
        >
          Add
        </button>
      </div>
      {values.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {values.map((v, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-seed-900/40 border border-seed-800/50 text-xs text-seed-400"
            >
              {v}
              <button
                type="button"
                onClick={() => remove(i)}
                className="text-seed-700 hover:text-seed-400 transition-colors leading-none"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/profile")
      .then((r) => r.json())
      .then((data) => {
        if (data.profile) setProfile({ ...EMPTY, ...data.profile });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const set = <K extends keyof Profile>(key: K, value: Profile[K]) =>
    setProfile((p) => ({ ...p, [key]: value }));

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = await fetch("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      if (!res.ok) throw new Error("Failed to save");
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-[#6b8f72] text-sm">
        Loading profile…
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#e8f5eb]">Company profile</h1>
        <p className="text-sm text-[#6b8f72] mt-1">
          Used to evaluate strategic fit and ground proposals in your capabilities.
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Company name */}
        <div>
          <label className="block text-xs text-[#6b8f72] mb-1.5">Company name</label>
          <input
            value={profile.company_name}
            onChange={(e) => set("company_name", e.target.value)}
            placeholder="Acme Consulting LLC"
            className="w-full bg-[#0d1610] border border-[#1e2d22] rounded-xl px-4 py-3 text-sm text-[#e8f5eb] placeholder-[#3d5c44] focus:outline-none focus:border-seed-700 transition-colors"
          />
        </div>

        <TagInput
          label="Industries"
          hint="Markets you serve"
          values={profile.industries}
          onChange={(v) => set("industries", v)}
        />

        <TagInput
          label="Core capabilities"
          hint="Your main technical or service competencies"
          values={profile.capabilities}
          onChange={(v) => set("capabilities", v)}
        />

        <TagInput
          label="Services offered"
          values={profile.services}
          onChange={(v) => set("services", v)}
        />

        <TagInput
          label="Certifications"
          hint="e.g. ISO 27001, CMMI Level 3, 8(a), WOSB"
          values={profile.certifications}
          onChange={(v) => set("certifications", v)}
        />

        <TagInput
          label="Geographies"
          hint="Regions or states where you operate"
          values={profile.geographies}
          onChange={(v) => set("geographies", v)}
        />

        <TagInput
          label="Past performance keywords"
          hint="Technologies and domains from past projects"
          values={profile.past_performance_keywords}
          onChange={(v) => set("past_performance_keywords", v)}
        />

        <TagInput
          label="Preferred project types"
          values={profile.preferred_project_types}
          onChange={(v) => set("preferred_project_types", v)}
        />

        <TagInput
          label="Excluded project types"
          hint="Work you will not bid on"
          values={profile.excluded_project_types}
          onChange={(v) => set("excluded_project_types", v)}
        />

        {/* Contract size */}
        <div>
          <label className="block text-xs text-[#6b8f72] mb-1.5">
            Target contract size (USD)
          </label>
          <div className="flex gap-3">
            <input
              type="number"
              value={profile.target_contract_size?.min ?? ""}
              onChange={(e) =>
                set("target_contract_size", {
                  ...profile.target_contract_size,
                  min: e.target.value ? Number(e.target.value) : undefined,
                })
              }
              placeholder="Min"
              className="flex-1 bg-[#0d1610] border border-[#1e2d22] rounded-xl px-4 py-3 text-sm text-[#e8f5eb] placeholder-[#3d5c44] focus:outline-none focus:border-seed-700 transition-colors"
            />
            <input
              type="number"
              value={profile.target_contract_size?.max ?? ""}
              onChange={(e) =>
                set("target_contract_size", {
                  ...profile.target_contract_size,
                  max: e.target.value ? Number(e.target.value) : undefined,
                })
              }
              placeholder="Max"
              className="flex-1 bg-[#0d1610] border border-[#1e2d22] rounded-xl px-4 py-3 text-sm text-[#e8f5eb] placeholder-[#3d5c44] focus:outline-none focus:border-seed-700 transition-colors"
            />
          </div>
        </div>

        {/* Actions */}
        {error && (
          <div className="p-4 rounded-xl bg-red-950/40 border border-red-900/50 text-sm text-red-300">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={saving}
          className="w-full py-3 rounded-xl bg-seed-600 hover:bg-seed-500 disabled:opacity-60 text-white font-semibold text-sm transition-colors"
        >
          {saving ? "Saving…" : saved ? "Saved ✓" : "Save profile"}
        </button>
      </form>
    </div>
  );
}
