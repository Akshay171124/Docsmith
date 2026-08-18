import { useMutation } from "@tanstack/react-query";
import { analyzePr } from "./api";
import AnalyzeForm from "./components/AnalyzeForm";
import ResultsPanel from "./components/ResultsPanel";

export default function App() {
  const mutation = useMutation({ mutationFn: analyzePr });

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-bold">Docsmith Playground</h1>
      <p className="mt-2 text-gray-600">
        Paste a public GitHub PR URL to see which docs it made stale — read-only, never posts.
      </p>
      <div className="mt-6">
        <AnalyzeForm onSubmit={(req) => mutation.mutate(req)} pending={mutation.isPending} />
      </div>
      {mutation.isError && (
        <p className="mt-4 rounded bg-red-100 p-3 text-sm text-red-800">
          {(mutation.error as Error).message}
        </p>
      )}
      {mutation.isSuccess && <ResultsPanel result={mutation.data} />}
    </main>
  );
}
