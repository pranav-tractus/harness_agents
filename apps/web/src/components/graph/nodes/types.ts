import type { Node, NodeProps } from "@xyflow/react";
import type { GraphNode } from "@/api/client";

export type NodeCounts = {
  chats?: number;
  contracts?: number;
  lines?: number;
  terms?: number;
};

export type FlowNodeData = {
  graphNode: GraphNode;
  expanded: boolean;
  hasChildren: boolean;
  onToggle: (id: string) => void;
  chatColor?: string;
  counts?: NodeCounts;
};

export type GraphFlowNode = Node<FlowNodeData>;

// Wrappers use the BASE NodeProps (data typed as Record<string, unknown>) and
// cast `data as FlowNodeData` internally. This keeps the `nodeTypes` registry
// assignable to React Flow's `NodeTypes` without variance errors.
export type GraphNodeProps = NodeProps;
