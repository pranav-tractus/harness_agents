import { describe, expect, it } from "vitest";
import type { GraphData } from "@/api/client";
import {
  assignChatColors,
  childrenMap,
  computeVisibleNodeIds,
  CONTAINMENT_EDGE_TYPES,
  hasHierarchyChildren,
  provenanceFor,
  rootIds,
  supersedesChain,
} from "./hierarchy";

function graph(): GraphData {
  return {
    nodes: [
      { id: "Customer::c1", label: "Acme", type: "Customer", properties: {} },
      { id: "Chat::ch1", label: "Chat A", type: "Chat", properties: {}, chat_id: "ch1" },
      { id: "Contract::k1", label: "rev1", type: "Contract", properties: {}, chat_id: "ch1" },
      { id: "Contract::k0", label: "rev0", type: "Contract", properties: {}, chat_id: "ch1" },
      { id: "MessageRef::m1", label: "#3 customer", type: "MessageRef", properties: { seq: 3, role: "customer", snippet: "we need 500" }, chat_id: "ch1" },
    ],
    edges: [
      { id: "e1", source: "Customer::c1", target: "Chat::ch1", type: "HAS_CHAT", properties: {} },
      { id: "e2", source: "Chat::ch1", target: "Contract::k1", type: "HAS_CONTRACT", properties: {} },
      { id: "e3", source: "Contract::k1", target: "MessageRef::m1", type: "DERIVED_FROM", properties: {} },
      { id: "e4", source: "Contract::k1", target: "Contract::k0", type: "SUPERSEDES", properties: {} },
    ],
  };
}

describe("hierarchy visibility", () => {
  it("treats Customer as root and hides collapsed chat's children", () => {
    const g = graph();
    const roots = rootIds(g.nodes, g.edges);
    expect(roots.has("Customer::c1")).toBe(true);
    const visible = computeVisibleNodeIds(g.nodes, g.edges, new Set());
    expect(visible.has("Customer::c1")).toBe(true);
    expect(visible.has("Chat::ch1")).toBe(true);
    expect(visible.has("Contract::k1")).toBe(false);
  });

  it("reveals a chat's contract children when the chat is expanded", () => {
    const g = graph();
    const visible = computeVisibleNodeIds(g.nodes, g.edges, new Set(["Chat::ch1"]));
    expect(visible.has("Contract::k1")).toBe(true);
    expect(visible.has("MessageRef::m1")).toBe(false);
  });

  it("flags nodes with hierarchy children (for carets)", () => {
    const g = graph();
    expect(hasHierarchyChildren("Chat::ch1", g.edges)).toBe(true);
    expect(hasHierarchyChildren("MessageRef::m1", g.edges)).toBe(false);
  });
});

describe("provenance and lineage", () => {
  it("returns MessageRefs derived from a contract", () => {
    const g = graph();
    const refs = provenanceFor(g.nodes[2], g);
    expect(refs.map((r) => r.id)).toEqual(["MessageRef::m1"]);
  });

  it("returns the MessageRef itself when selected directly", () => {
    const g = graph();
    const refs = provenanceFor(g.nodes[4], g);
    expect(refs.map((r) => r.id)).toEqual(["MessageRef::m1"]);
  });

  it("follows the SUPERSEDES chain", () => {
    const g = graph();
    const chain = supersedesChain("Contract::k1", g);
    expect(chain.map((c) => c.id)).toEqual(["Contract::k0"]);
  });
});

describe("assignChatColors", () => {
  it("assigns a stable color per chat id", () => {
    const colors = assignChatColors(["ch1", "ch2"]);
    expect(colors.ch1).toBeTruthy();
    expect(colors.ch2).toBeTruthy();
    expect(colors.ch1).not.toBe(colors.ch2);
  });
});

describe("cross-link edges", () => {
  it("treats CONTINUES as a cross-link, not containment", () => {
    expect(CONTAINMENT_EDGE_TYPES.has("CONTINUES")).toBe(false);
    const kids = childrenMap([
      { id: "e", source: "Chat::b", target: "Chat::a", type: "CONTINUES", properties: {} },
    ]);
    expect(kids.size).toBe(0); // CONTINUES does not create parent→child nesting
  });
});
