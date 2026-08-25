import { useMutation } from "@tanstack/react-query";
import { analyzePr } from "./api";
import AnalyzeForm from "./components/AnalyzeForm";
import ResultsPanel from "./components/ResultsPanel";

const REPO_URL = "https://github.com/Akshay171124/Docsmith";

function Spark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <path
        d="M16 4 L18.6 13.4 L28 16 L18.6 18.6 L16 28 L13.4 18.6 L4 16 L13.4 13.4 Z"
        fill="currentColor"
      />
    </svg>
  );
}

export default function App() {
  const mutation = useMutation({ mutationFn: analyzePr });

  return (
    <div className="min-h-screen">
      {/* Brand bar */}
      <header className="mx-auto flex max-w-3xl items-center justify-between px-5 py-5">
        <div className="flex items-center gap-2">
          <Spark className="h-5 w-5 text-ember" />
          <span className="font-display text-lg font-bold tracking-tight">Docsmith</span>
        </div>
        <a
          href={REPO_URL}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-xs text-muted transition-colors hover:text-fg"
        >
          github ↗
        </a>
      </header>

      {/* Hero */}
      <div className="relative overflow-hidden">
        <div className="ember-glow pointer-events-none absolute inset-x-0 top-0 h-72" />
        <div className="grid-floor pointer-events-none absolute inset-x-0 top-0 h-72" />
        <main className="relative mx-auto max-w-3xl px-5 pb-24 pt-10">
          <p className="flex items-center gap-2 font-mono text-xs uppercase tracking-[0.2em] text-ember">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-ember shadow-ember" />
            documentation staleness engine
          </p>

          <h1 className="mt-5 font-display text-4xl font-bold leading-[1.05] tracking-tight sm:text-5xl">
            Catch the docs your pull
            <br />
            request just made <span className="text-ember">wrong.</span>
          </h1>

          <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-muted">
            Paste a public GitHub PR. Docsmith reads the code changes, finds the documentation
            that now describes them incorrectly, and drafts the fix — read-only, it never
            touches your repo.
          </p>

          {/* Pipeline — the actual stages, in the tool's own words */}
          <div className="mt-6 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[11px] text-faint">
            {["git diff", "changed symbols", "linked docs", "llm verdict", "proposed fix"].map(
              (stage, i) => (
                <span key={stage} className="flex items-center gap-2">
                  {i > 0 && <span className="text-ember/60">→</span>}
                  <span className="text-muted">{stage}</span>
                </span>
              ),
            )}
          </div>

          {/* The console */}
          <div className="mt-8">
            <AnalyzeForm onSubmit={(req) => mutation.mutate(req)} pending={mutation.isPending} />
          </div>

          {mutation.isError && (
            <div className="mt-5 flex items-start gap-3 rounded-lg border border-del/40 bg-del/10 p-4">
              <span className="mt-0.5 font-mono text-sm text-del">!</span>
              <div>
                <p className="font-mono text-xs uppercase tracking-wider text-del">
                  analysis failed
                </p>
                <p className="mt-1 text-sm text-fg">{(mutation.error as Error).message}</p>
              </div>
            </div>
          )}

          {mutation.isSuccess && <ResultsPanel result={mutation.data} />}

          <footer className="mt-16 border-t border-line pt-5 font-mono text-[11px] leading-relaxed text-faint">
            read-only · public repos only · your key is used for one request and never stored ·
            $0 on a local Ollama model
          </footer>
        </main>
      </div>
    </div>
  );
}
