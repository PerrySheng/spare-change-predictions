export const AGENTS = ["News Scout", "Base Rate Analyst", "Market Reader", "Skeptic"] as const;
export type Agent = typeof AGENTS[number];
export type Source = {url: string; title: string; snippet?: string};
export type Estimate = {probability: number; confidence: "low" | "medium" | "high"; reasons: string[]; sources: string[]; revision_reason?: string};
export type Packet = {type: string; data: Record<string, unknown>};

export function safeUrl(value: unknown): value is string {
  if (typeof value !== "string" || value.length > 2048 || /[\s\x00-\x1f\x7f]/.test(value)) return false;
  try { const u = new URL(value); return ["http:", "https:"].includes(u.protocol) && !!u.hostname && !u.username && !u.password; } catch { return false; }
}

export function validateEstimate(value: unknown, allowedSources: Set<string>, revision = false): Estimate {
  if (!value || typeof value !== "object") throw new Error("Agent returned invalid estimate JSON.");
  const e = value as Record<string, unknown>;
  if (typeof e.probability !== "number" || !Number.isFinite(e.probability) || e.probability < 0 || e.probability > 1) throw new Error("Agent probability is outside 0–1.");
  if (!["low", "medium", "high"].includes(String(e.confidence))) throw new Error("Agent confidence is invalid.");
  if (!Array.isArray(e.reasons) || e.reasons.length !== 3 || e.reasons.some(r => typeof r !== "string" || !r.trim() || r.length > 500)) throw new Error("Each estimate needs exactly three short reasons.");
  if (!Array.isArray(e.sources) || e.sources.length > 15 || e.sources.some(s => !safeUrl(s) || !allowedSources.has(s))) throw new Error("Agent cited a source that was not observed in the provided evidence or search results.");
  if (revision && (typeof e.revision_reason !== "string" || !e.revision_reason.trim() || e.revision_reason.length > 700)) throw new Error("Revision requires a brief explanation.");
  return e as unknown as Estimate;
}

export function median(values: number[]): number {
  if (values.length !== 4 || values.some(v => !Number.isFinite(v) || v < 0 || v > 1)) throw new Error("Four valid estimates are required.");
  const ordered = [...values].sort((a,b) => a-b);
  return (ordered[1] + ordered[2]) / 2;
}

export function parseFinal(text: string): unknown {
  const stripped = text.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  return JSON.parse(stripped);
}

export function allowSearch(agent: Agent, round: number, sharedSources: Source[]): boolean {
  return round === 1 && agent !== "Market Reader" && sharedSources.length === 0;
}
