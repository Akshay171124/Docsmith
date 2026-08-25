import type { SectionResult } from "../types";

const ROUTE: Record<string, { label: string; cls: string }> = {
  autofix: { label: "ready to fix", cls: "border-add/40 bg-add/10 text-add" },
  flag: { label: "needs review", cls: "border-amber/40 bg-amber/10 text-amber" },
  skipped: { label: "skipped", cls: "border-line bg-raise text-muted" },
};

type DiffLine = { gutter: string; body: string; cls: string; rowCls: string };

function classifyDiff(line: string): DiffLine {
  if (line.startsWith("+++") || line.startsWith("---"))
    return { gutter: " ", body: line, cls: "text-faint", rowCls: "" };
  if (line.startsWith("@@"))
    return { gutter: " ", body: line, cls: "text-ember/80", rowCls: "" };
  if (line.startsWith("+"))
    return { gutter: "+", body: line.slice(1), cls: "text-add", rowCls: "bg-add/[0.07]" };
  if (line.startsWith("-"))
    return { gutter: "-", body: line.slice(1), cls: "text-del", rowCls: "bg-del/[0.07]" };
  return {
    gutter: " ",
    body: line.startsWith(" ") ? line.slice(1) : line,
    cls: "text-muted",
    rowCls: "",
  };
}

function HeatMeter({ value }: { value: number }) {
  const filled = Math.round(value * 10);
  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-[3px]">
        {Array.from({ length: 10 }).map((_, i) => (
          <span
            key={i}
            className={`h-3 w-1.5 rounded-[1px] ${i < filled ? "bg-ember" : "bg-line"}`}
          />
        ))}
      </div>
      <span className="font-mono text-xs text-muted">{Math.round(value * 100)}%</span>
    </div>
  );
}

export default function SectionCard({ section }: { section: SectionResult }) {
  const route = ROUTE[section.route] ?? ROUTE.skipped;

  return (
    <article className="animate-fade-up overflow-hidden rounded-xl border border-line bg-panel">
      {/* File-tab header */}
      <header className="flex items-center justify-between gap-3 border-b border-line bg-raise px-4 py-2.5">
        <code className="truncate font-mono text-sm text-fg">{section.section_id}</code>
        <span
          className={`shrink-0 rounded-full border px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${route.cls}`}
        >
          {route.label}
        </span>
      </header>

      <div className="space-y-4 p-4">
        {/* Verdict line */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="font-mono text-[11px] uppercase tracking-wider text-faint">
            staleness confidence
          </span>
          <HeatMeter value={section.confidence} />
        </div>

        <p className="text-sm leading-relaxed text-fg">{section.reason}</p>

        {section.wrong_claims.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[11px] uppercase tracking-wider text-faint">
              now inaccurate
            </span>
            {section.wrong_claims.map((claim) => (
              <code
                key={claim}
                className="rounded border border-del/30 bg-del/5 px-1.5 py-0.5 font-mono text-xs text-del/90"
              >
                {claim}
              </code>
            ))}
          </div>
        )}

        {section.diff && (
          <div className="overflow-hidden rounded-lg border border-line">
            <div className="border-b border-line bg-raise px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-faint">
              proposed fix
            </div>
            <div className="scroll-thin overflow-x-auto bg-ink py-2">
              {section.diff.split("\n").map((line, i) => {
                const d = classifyDiff(line);
                return (
                  <div key={i} className={`flex ${d.rowCls}`}>
                    <span className="w-6 shrink-0 select-none text-center font-mono text-xs text-faint">
                      {d.gutter}
                    </span>
                    <span className={`whitespace-pre pr-4 font-mono text-xs ${d.cls}`}>
                      {d.body || " "}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </article>
  );
}
