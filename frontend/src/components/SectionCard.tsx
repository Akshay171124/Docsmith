import type { SectionResult } from "../types";

const ROUTE_STYLE: Record<string, string> = {
  autofix: "bg-green-100 text-green-800",
  flag: "bg-yellow-100 text-yellow-800",
  skipped: "bg-gray-100 text-gray-600",
};

export default function SectionCard({ section }: { section: SectionResult }) {
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center justify-between">
        <code className="font-mono text-sm">{section.section_id}</code>
        <span className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${ROUTE_STYLE[section.route] ?? ""}`}>
          {section.route}
        </span>
      </div>
      <p className="mt-2 text-sm text-gray-700">{section.reason}</p>
      <div className="mt-2 h-1.5 w-full rounded bg-gray-200">
        <div className="h-1.5 rounded bg-blue-500" style={{ width: `${Math.round(section.confidence * 100)}%` }} />
      </div>
      {section.wrong_claims.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-sm text-gray-600">
          {section.wrong_claims.map((claim) => <li key={claim}>{claim}</li>)}
        </ul>
      )}
      {section.diff && (
        <pre className="mt-3 overflow-x-auto rounded bg-gray-900 p-3 text-xs text-gray-100">{section.diff}</pre>
      )}
    </div>
  );
}
