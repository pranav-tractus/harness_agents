import { describe, expect, it } from "vitest";
import { parseAgentTag, splitAgentMention } from "./agentTag";

describe("parseAgentTag", () => {
  it("flags non-tagged messages as not-agent", () => {
    expect(parseAgentTag("hello there")).toEqual({ isAgent: false, action: "ask" });
  });
  it("routes a plain @agent message to ask", () => {
    expect(parseAgentTag("@agent create sales order")).toEqual({ isAgent: true, action: "ask" });
  });
  it("routes confirm keywords to approve (case-insensitive)", () => {
    for (const w of ["confirm", "Finalize", "APPROVE"]) {
      expect(parseAgentTag(`@agent ${w}`)).toEqual({ isAgent: true, action: "approve" });
    }
  });
  it("treats @agent with no verb as ask", () => {
    expect(parseAgentTag("@agent")).toEqual({ isAgent: true, action: "ask" });
  });
});

describe("splitAgentMention", () => {
  it("splits the leading @agent token from the rest", () => {
    expect(splitAgentMention("@agent create sales order")).toEqual({
      mention: "@agent",
      rest: " create sales order",
    });
  });
  it("returns null mention when not tagged", () => {
    expect(splitAgentMention("hello")).toEqual({ mention: null, rest: "hello" });
  });
});
