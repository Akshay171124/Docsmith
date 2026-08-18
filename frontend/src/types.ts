export interface AnalyzeRequest {
  pr_url: string;
  backend: "ollama" | "claude" | "fake";
  api_key?: string | null;
  ollama_host?: string | null;
  model?: string | null;
}

export interface SectionResult {
  file: string;
  section_id: string;
  route: string;
  confidence: number;
  reason: string;
  wrong_claims: string[];
  diff: string;
}

export interface AnalyzeResult {
  summary: { verified: number; auto_fixable: number; flagged: number; skipped: number };
  results: SectionResult[];
}
