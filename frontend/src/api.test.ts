import { afterEach, describe, expect, it, vi } from "vitest";
import { analyzePr } from "./api";
import type { AnalyzeResult } from "./types";

const RESULT: AnalyzeResult = {
  summary: { verified: 1, auto_fixable: 1, flagged: 0, skipped: 0 },
  results: [
    {
      file: "README.md", section_id: "README.md#users", symbol_id: "create_user",
      route: "autofix",
      confidence: 0.9, reason: "signature changed", wrong_claims: ["create_user"],
      diff: "-old\n+new",
    },
  ],
};

afterEach(() => vi.restoreAllMocks());

describe("analyzePr", () => {
  it("posts and parses the result", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(RESULT), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const out = await analyzePr({ pr_url: "https://github.com/o/r/pull/1", backend: "fake" });
    expect(out.summary.auto_fixable).toBe(1);
    expect(out.results[0].section_id).toBe("README.md#users");
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("throws with the API detail on error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "bad url" }), { status: 400 }),
    ));
    await expect(analyzePr({ pr_url: "x", backend: "fake" })).rejects.toThrow("bad url");
  });
});
