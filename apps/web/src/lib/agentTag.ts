export type AgentAction = "ask" | "approve";

const AGENT_TAG = /^@agent\b/i;
const CONFIRM_WORDS = new Set(["confirm", "finalize", "approve"]);

export function parseAgentTag(body: string): { isAgent: boolean; action: AgentAction } {
  const trimmed = body.trim();
  if (!AGENT_TAG.test(trimmed)) return { isAgent: false, action: "ask" };
  const rest = trimmed.replace(AGENT_TAG, "").trim();
  const first = (rest.split(/\s+/)[0] ?? "").toLowerCase();
  return { isAgent: true, action: CONFIRM_WORDS.has(first) ? "approve" : "ask" };
}

export function splitAgentMention(body: string): { mention: string | null; rest: string } {
  const m = body.match(/^(@agent)\b(.*)$/i);
  if (!m) return { mention: null, rest: body };
  return { mention: m[1], rest: m[2] };
}
