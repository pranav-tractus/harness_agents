export type LayerId = "context" | "flows" | "agent";
export type FlowId = "autonomous" | "approve" | "manual";
export type NodeKind = "ui" | "router" | "service" | "store" | "external" | "gate";
export type EdgeKind = "call" | "data" | "gate-fail";

export type ArchNode = {
  id: string;
  label: string;
  kind: NodeKind;
  layer: LayerId;
  /** Visual cluster, e.g. "API" | "Stores" | "Agent core". */
  group?: string;
  /** Which request flows touch this node. Drives dimming on the flows layer. */
  flows?: FlowId[];
  /** Source anchor as `path::symbol`. Never `path:line` — line numbers rot. */
  anchor?: string;
  /** Detail-panel body. One or two sentences. */
  summary: string;
  reads?: string[];
  writes?: string[];
  /** The rule this unit guarantees, if any. */
  invariant?: string;
};

export type ArchEdge = {
  id: string;
  source: string;
  target: string;
  label?: string;
  layer: LayerId;
  flows?: FlowId[];
  kind: EdgeKind;
};

export const LAYERS: { id: LayerId; label: string; blurb: string }[] = [
  {
    id: "context",
    label: "System context",
    blurb: "What the system is made of and what it talks to.",
  },
  {
    id: "flows",
    label: "Request flows",
    blurb: "Which code runs when a request hits each entrypoint.",
  },
  {
    id: "agent",
    label: "Agent internals",
    blurb: "How a draft gets made, and what gates a commit.",
  },
];

export const FLOWS: { id: FlowId; label: string; color: string }[] = [
  { id: "autonomous", label: "Autonomous draft", color: "#6366f1" },
  { id: "approve", label: "Approve / finalize", color: "#10b981" },
  { id: "manual", label: "Manual command", color: "#f59e0b" },
];
