import { describe, expect, it } from "vitest";
import { splitAgentMention } from "./agentTag";

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
