import type { AnalyzeResult } from "../types";
import SectionCard from "./SectionCard";

export default function ResultsPanel({ result }: { result: AnalyzeResult }) {
  const s = result.summary;
  return (
    <section className="mt-6">
      <p className="text-sm font-medium">
        {s.verified} verified · {s.auto_fixable} auto-fixable · {s.flagged} flagged · {s.skipped} skipped
      </p>
      <div className="mt-4 space-y-3">
        {result.results.map((section) => <SectionCard key={section.section_id} section={section} />)}
        {result.results.length === 0 && (
          <p className="text-sm text-gray-500">No stale documentation found for this PR. 🎉</p>
        )}
      </div>
    </section>
  );
}
