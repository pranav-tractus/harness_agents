import type { ComponentType } from "react";
import { LeafNode } from "./LeafNode";
import type { GraphNodeProps } from "./types";

// Extended in Task 5 with Chat/Contract/LineItem/Term components.
export const nodeTypes: Record<string, ComponentType<GraphNodeProps>> = {
  Customer: LeafNode,
  Product: LeafNode,
  Port: LeafNode,
  MessageRef: LeafNode,
  Attribute: LeafNode,
  Preference: LeafNode,
  Category: LeafNode,
  Application: LeafNode,
  Alias: LeafNode,
  SpecAttr: LeafNode,
};

export type { FlowNodeData, GraphFlowNode, GraphNodeProps, NodeCounts } from "./types";
