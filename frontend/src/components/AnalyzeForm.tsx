import { useState } from "react";
import type { AnalyzeRequest } from "../types";

const EXAMPLE = "https://github.com/octocat/Hello-World/pull/1";

export default function AnalyzeForm({
  onSubmit,
  pending,
}: {
  onSubmit: (req: AnalyzeRequest) => void;
  pending: boolean;
}) {
  const [prUrl, setPrUrl] = useState(EXAMPLE);
  const [backend, setBackend] = useState<"ollama" | "claude">("ollama");
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

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label htmlFor="pr" className="block text-sm font-medium">Public GitHub PR URL</label>
        <input id="pr" value={prUrl} onChange={(e) => setPrUrl(e.target.value)}
          className="mt-1 w-full rounded border p-2 font-mono text-sm" />
      </div>
      <fieldset className="flex gap-4">
        <label className="flex items-center gap-1 text-sm">
          <input type="radio" name="backend" checked={backend === "ollama"}
            onChange={() => setBackend("ollama")} /> Ollama (local)
        </label>
        <label className="flex items-center gap-1 text-sm">
          <input type="radio" name="backend" checked={backend === "claude"}
            onChange={() => setBackend("claude")} /> Claude
        </label>
      </fieldset>
      <div>
        <label htmlFor="cred" className="block text-sm font-medium">
          {backend === "claude" ? "Anthropic API key" : "Ollama host"}
        </label>
        <input id="cred" value={credential} onChange={(e) => setCredential(e.target.value)}
          type={backend === "claude" ? "password" : "text"}
          placeholder={backend === "claude" ? "sk-ant-…" : "http://localhost:11434"}
          className="mt-1 w-full rounded border p-2 text-sm" />
      </div>
      <div>
        <label htmlFor="model" className="block text-sm font-medium">Model (optional)</label>
        <input id="model" value={model} onChange={(e) => setModel(e.target.value)}
          className="mt-1 w-full rounded border p-2 text-sm" />
      </div>
      <button type="submit" disabled={pending}
        className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">
        {pending ? "Analyzing…" : "Analyze"}
      </button>
    </form>
  );
}
