import { useState } from "react";
import type { AnalyzeRequest } from "../types";

const EXAMPLE = "https://github.com/octocat/Hello-World/pull/1";

type Backend = "ollama" | "claude";

export default function AnalyzeForm({
  onSubmit,
  pending,
}: {
  onSubmit: (req: AnalyzeRequest) => void;
  pending: boolean;
}) {
  const [prUrl, setPrUrl] = useState(EXAMPLE);
  const [backend, setBackend] = useState<Backend>("ollama");
  const [credential, setCredential] = useState("");
  const [model, setModel] = useState("");

  function submit(event: React.FormEvent) {
    event.preventDefault();
    onSubmit({
      pr_url: prUrl,
      backend,
      api_key: backend === "claude" ? credential || null : null,
      ollama_host: backend === "ollama" ? credential || null : null,
      model: model || null,
    });
  }

  const isClaude = backend === "claude";
  const inputClass =
    "w-full rounded-md border border-line bg-ink px-3 py-2.5 font-mono text-sm text-fg " +
    "placeholder:text-faint outline-none transition focus:border-ember focus:shadow-ember";

  return (
    <form
      onSubmit={submit}
      className="overflow-hidden rounded-xl border border-line bg-panel shadow-panel"
    >
      {/* Window chrome */}
      <div className="flex items-center justify-between border-b border-line bg-raise px-4 py-2.5">
        <span className="font-mono text-xs text-muted">
          <span className="text-ember">docsmith</span> analyze --pr
        </span>
        <div className="flex rounded-md border border-line p-0.5">
          {(["ollama", "claude"] as const).map((value) => {
            const active = backend === value;
            return (
              <label
                key={value}
                className={
                  "cursor-pointer rounded px-2.5 py-1 font-mono text-xs transition " +
                  (active ? "bg-ember text-ink" : "text-muted hover:text-fg")
                }
              >
                <input
                  type="radio"
                  name="backend"
                  className="sr-only"
                  checked={active}
                  onChange={() => {
                    setBackend(value);
                    setCredential("");
                  }}
                />
                {value === "ollama" ? "Ollama" : "Claude"}
              </label>
            );
          })}
        </div>
      </div>

      {/* Body */}
      <div className="space-y-4 p-5">
        <div>
          <label
            htmlFor="pr"
            className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted"
          >
            Public GitHub PR URL
          </label>
          <input
            id="pr"
            value={prUrl}
            onChange={(e) => setPrUrl(e.target.value)}
            placeholder="https://github.com/owner/repo/pull/123"
            className={inputClass}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
          <div>
            <label
              htmlFor="cred"
              className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted"
            >
              {isClaude ? "Anthropic API key" : "Ollama host"}
            </label>
            <input
              id="cred"
              value={credential}
              onChange={(e) => setCredential(e.target.value)}
              type={isClaude ? "password" : "text"}
              placeholder={isClaude ? "sk-ant-…" : "http://localhost:11434"}
              className={inputClass}
            />
          </div>
          <div>
            <label
              htmlFor="model"
              className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted"
            >
              Model <span className="text-faint">(optional)</span>
            </label>
            <input
              id="model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={isClaude ? "claude-sonnet-5" : "qwen2.5-coder:7b"}
              className={`${inputClass} sm:w-52`}
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={pending}
          className="group flex w-full items-center justify-center gap-2 rounded-md bg-ember px-4 py-2.5 font-medium text-ink transition hover:bg-ember-2 focus-visible:shadow-ember disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
        >
          {pending ? (
            <>
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink" />
              Analyzing…
            </>
          ) : (
            <>
              Analyze PR
              <span className="transition-transform group-hover:translate-x-0.5">→</span>
            </>
          )}
        </button>
      </div>
    </form>
  );
}
