import { describe, expect, it } from "vitest";
import { edgeStroke } from "./GraphCanvas";

describe("edgeStroke", () => {
  it("colors CONTINUES distinctly from SUPERSEDES and default", () => {
    expect(edgeStroke("SUPERSEDES")).toBe("#f43f5e");
    expect(edgeStroke("CONTINUES")).toBe("#6366f1");
    expect(edgeStroke("HAS_CHAT")).toBe("#cbd5e1");
  });
});
