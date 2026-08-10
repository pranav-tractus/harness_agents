import type { GraphData, GraphEdge, GraphNode } from "@/api/client";

// Edge types whose source "contains" its target in the drill-down hierarchy.
// SUPERSEDES is intentionally excluded — it's a cross-link between revisions,
// not a containment edge.
export const CONTAINMENT_EDGE_TYPES = new Set<string>([
  "HAS_ATTRIBUTE",
  "PREFERS",
  "HAS_CHAT",
  "HAS_CONTRACT",
  "HAS_LINE",
  "HAS_TERM",
  "DERIVED_FROM",
  "OF_PRODUCT",
  "SHIP_TO",
  "HAS_SPEC",
  "IN_CATEGORY",
  "USED_FOR",
]);

export function childrenMap(edges: GraphEdge[]): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const e of edges) {
    if (!CONTAINMENT_EDGE_TYPES.has(e.type)) continue;
    const arr = map.get(e.source) ?? [];
    arr.push(e.target);
    map.set(e.source, arr);
  }
  return map;
}

export function rootIds(nodes: GraphNode[], edges: GraphEdge[]): Set<string> {
  const containedTargets = new Set<string>();
  for (const e of edges) {
    if (CONTAINMENT_EDGE_TYPES.has(e.type)) containedTargets.add(e.target);
  }
  return new Set(nodes.map((n) => n.id).filter((id) => !containedTargets.has(id)));
}

export function hasHierarchyChildren(id: string, edges: GraphEdge[]): boolean {
  return edges.some((e) => CONTAINMENT_EDGE_TYPES.has(e.type) && e.source === id);
}

// A node reveals its children if it is a root (always shown/expanded) or its id
// is in the `expanded` set. Roots are visible unconditionally; every other node
// is visible only if reached from a revealing ancestor.
export function computeVisibleNodeIds(
  nodes: GraphNode[],
  edges: GraphEdge[],
  expanded: Set<string>,
): Set<string> {
  const roots = rootIds(nodes, edges);
  const children = childrenMap(edges);
  const visible = new Set<string>();
  const queue: string[] = [];
  for (const n of nodes) {
    if (roots.has(n.id)) {
      visible.add(n.id);
      queue.push(n.id);
    }
  }
  while (queue.length > 0) {
    const id = queue.shift() as string;
    const reveals = roots.has(id) || expanded.has(id);
    if (!reveals) continue;
    for (const child of children.get(id) ?? []) {
      if (!visible.has(child)) {
        visible.add(child);
        queue.push(child);
      }
    }
  }
  return visible;
}

function parentMap(edges: GraphEdge[]): Map<string, string> {
  const map = new Map<string, string>();
  for (const e of edges) {
    if (CONTAINMENT_EDGE_TYPES.has(e.type)) map.set(e.target, e.source);
  }
  return map;
}

function contractAncestor(id: string, graph: GraphData): string | null {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const parents = parentMap(graph.edges);
  let cur: string | undefined = id;
  for (let i = 0; i < 32 && cur; i += 1) {
    const node = byId.get(cur);
    if (!node) return null;
    if (node.type === "Contract") return cur;
    cur = parents.get(cur);
  }
  return null;
}

// Provenance = the MessageRefs a fact was derived from. A MessageRef resolves to
// itself; anything else resolves to its ancestor Contract's DERIVED_FROM refs.
export function provenanceFor(node: GraphNode, graph: GraphData): GraphNode[] {
  if (node.type === "MessageRef") return [node];
  const contractId = contractAncestor(node.id, graph) ?? node.id;
  const refIds = new Set(
    graph.edges
      .filter((e) => e.type === "DERIVED_FROM" && e.source === contractId)
      .map((e) => e.target),
  );
  return graph.nodes.filter((n) => refIds.has(n.id));
}

export function supersedesChain(contractId: string, graph: GraphData): GraphNode[] {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const next = new Map<string, string>();
  for (const e of graph.edges) {
    if (e.type === "SUPERSEDES") next.set(e.source, e.target);
  }
  const chain: GraphNode[] = [];
  const seen = new Set<string>();
  let cur = next.get(contractId);
  while (cur && !seen.has(cur)) {
    seen.add(cur);
    const node = byId.get(cur);
    if (node) chain.push(node);
    cur = next.get(cur);
  }
  return chain;
}

const CHAT_PALETTE = [
  "#6366f1",
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#ec4899",
  "#8b5cf6",
  "#14b8a6",
  "#f43f5e",
];

export function assignChatColors(chatIds: string[]): Record<string, string> {
  const unique = Array.from(new Set(chatIds)).sort();
  const out: Record<string, string> = {};
  unique.forEach((id, i) => {
    out[id] = CHAT_PALETTE[i % CHAT_PALETTE.length];
  });
  return out;
}
