interface RequirementItem {
  text: string;
  category: "mandatory" | "optional" | "unclear";
  reason?: string;
  type?: "technical" | "administrative" | "unclear";
  type_reason?: string;
}

interface Requirements {
  summary?: string;
  client?: string | null;
  deadline?: string | null;
  budget?: string | null;
  requirements?: (string | RequirementItem)[];
  evaluation_criteria?: string[];
  deliverables?: string[];
  keywords?: string[];
}

interface Props {
  requirements: Requirements;
}

function InfoRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="flex gap-3">
      <span className="text-xs text-[#6b8f72] w-20 shrink-0 pt-0.5">{label}</span>
      <span className="text-sm text-[#e8f5eb]">{value}</span>
    </div>
  );
}

function StringList({ items, color = "seed" }: { items?: string[]; color?: string }) {
  if (!items?.length) return <p className="text-sm text-[#6b8f72]">None identified</p>;
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-sm">
          <span className={`text-${color}-500 mt-0.5 shrink-0`}>▸</span>
          <span className="text-[#d1fae5]">{item}</span>
        </li>
      ))}
    </ul>
  );
}

const CATEGORY_STYLES: Record<string, string> = {
  mandatory: "bg-red-950/40 border-red-900/50 text-red-400",
  optional:  "bg-blue-950/40 border-blue-900/50 text-blue-400",
  unclear:   "bg-[#1e2d22] border-[#1e2d22] text-[#6b8f72]",
};

const TYPE_STYLES: Record<string, string> = {
  technical:      "bg-purple-950/40 border-purple-900/50 text-purple-400",
  administrative: "bg-yellow-950/40 border-yellow-900/50 text-yellow-500",
  unclear:        "bg-[#1e2d22] border-[#1e2d22] text-[#6b8f72]",
};

function RequirementsList({ items }: { items?: (string | RequirementItem)[] }) {
  if (!items?.length) return <p className="text-sm text-[#6b8f72]">None identified</p>;
  return (
    <ul className="space-y-2">
      {items.map((item, i) => {
        const isObj = typeof item === "object" && item !== null;
        const text       = isObj ? item.text        : item;
        const category   = isObj ? item.category    : null;
        const reason     = isObj ? item.reason      : null;
        const type       = isObj ? item.type        : null;
        const typeReason = isObj ? item.type_reason : null;
        return (
          <li key={i} className="flex gap-2 text-sm">
            <span className="text-seed-500 mt-0.5 shrink-0">▸</span>
            <div className="flex-1 min-w-0">
              <span className="text-[#d1fae5]">{text}</span>
              {category && (
                <span
                  className={`ml-2 text-[10px] px-1.5 py-0.5 rounded border align-middle ${CATEGORY_STYLES[category] ?? CATEGORY_STYLES.unclear}`}
                  title={reason ?? undefined}
                >
                  {category}
                </span>
              )}
              {type && (
                <span
                  className={`ml-1 text-[10px] px-1.5 py-0.5 rounded border align-middle ${TYPE_STYLES[type] ?? TYPE_STYLES.unclear}`}
                  title={typeReason ?? undefined}
                >
                  {type}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs uppercase tracking-widest text-[#6b8f72] mb-3">{title}</h3>
      {children}
    </div>
  );
}

export default function RequirementsView({ requirements }: Props) {
  const hasMetadata = requirements.client || requirements.deadline || requirements.budget;

  return (
    <div className="rounded-2xl border border-[#1e2d22] bg-[#111a14] p-6 space-y-6">
      {requirements.summary && (
        <Section title="Summary">
          <p className="text-sm text-[#d1fae5] leading-relaxed">{requirements.summary}</p>
        </Section>
      )}

      {hasMetadata && (
        <Section title="Key Details">
          <div className="space-y-2">
            <InfoRow label="Client" value={requirements.client} />
            <InfoRow label="Deadline" value={requirements.deadline} />
            <InfoRow label="Budget" value={requirements.budget} />
          </div>
        </Section>
      )}

      <Section title="Requirements">
        <RequirementsList items={requirements.requirements} />
      </Section>

      <Section title="Deliverables">
        <StringList items={requirements.deliverables} color="blue" />
      </Section>

      <Section title="Evaluation Criteria">
        <StringList items={requirements.evaluation_criteria} color="yellow" />
      </Section>

      {requirements.keywords?.length ? (
        <Section title="Keywords">
          <div className="flex flex-wrap gap-2">
            {requirements.keywords.map((kw, i) => (
              <span
                key={i}
                className="text-xs px-2.5 py-1 rounded-full bg-seed-900/40 border border-seed-800/50 text-seed-300"
              >
                {kw}
              </span>
            ))}
          </div>
        </Section>
      ) : null}
    </div>
  );
}
