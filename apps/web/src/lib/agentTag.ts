/** Splits the leading @agent token so ChatPane can render it as a chip.
 *  Purely cosmetic — the server decides what a tag actually does. */
export function splitAgentMention(body: string): { mention: string | null; rest: string } {
  const m = body.match(/^(@agent)\b(.*)$/i);
  if (!m) return { mention: null, rest: body };
  return { mention: m[1], rest: m[2] };
}
