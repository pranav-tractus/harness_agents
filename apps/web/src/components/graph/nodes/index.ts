import type { ComponentType } from "react";
import { BranchNode } from "./BranchNode";
import { ContractNode } from "./ContractNode";
import { LeafNode } from "./LeafNode";
import { LineItemNode } from "./LineItemNode";
import { TermNode } from "./TermNode";
import type { GraphNodeProps } from "./types";

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
  Chat: BranchNode,
  Contract: ContractNode,
  LineItem: LineItemNode,
  Term: TermNode,
};

export type { FlowNodeData, GraphFlowNode, GraphNodeProps, NodeCounts } from "./types";
