import type { AnalyzeResult } from "../types";
import SectionCard from "./SectionCard";

function Metric({ value, label, dot }: { value: number; label: string; dot: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${dot}`} />
      <span className="font-mono text-lg text-fg">{value}</span>
      <span className="font-mono text-[11px] uppercase tracking-wider text-faint">{label}</span>
    </div>
  );
}

export default function ResultsPanel({ result }: { result: AnalyzeResult }) {
  const s = result.summary;

  return (
    <section className="mt-8">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border border-line bg-panel px-5 py-4">
        <Metric value={s.verified} label="verified" dot="bg-add" />
        <Metric value={s.auto_fixable} label="ready to fix" dot="bg-ember" />
        <Metric value={s.flagged} label="needs review" dot="bg-amber" />
        <Metric value={s.skipped} label="skipped" dot="bg-faint" />
      </div>

      <div className="mt-4 space-y-4">
        {result.results.map((section) => (
          <SectionCard key={`${section.symbol_id}::${section.section_id}`} section={section} />
        ))}

        {result.results.length === 0 && (
          <div className="flex items-center gap-3 rounded-xl border border-add/30 bg-add/[0.06] px-5 py-6">
            <span className="font-mono text-add">✓</span>
            <p className="text-sm text-fg">
              Documentation is in sync with this pull request — nothing looks stale.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
