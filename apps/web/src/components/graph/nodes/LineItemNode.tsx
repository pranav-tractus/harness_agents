import { Handle, Position } from "@xyflow/react";
import type { GraphNode } from "@/api/client";
import {
  AgreementGlyph,
  ExpandCaret,
  InferredTag,
  NODE_COLORS,
  NodeShell,
  isInferred,
} from "./parts";
import type { FlowNodeData, GraphNodeProps } from "./types";

function str(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}

export function LineItemContent({
  node,
  expanded,
  hasChildren,
  onToggle,
  chatColor,
}: {
  node: GraphNode;
  expanded: boolean;
  hasChildren: boolean;
  onToggle: () => void;
  chatColor?: string;
}) {
  const p = node.properties;
  const inferred = isInferred(node);
  const qty = `${str(p.quantity) || "?"} ${str(p.unit)}`.trim();
  const price = `${str(p.price) || "?"} ${str(p.price_unit)}`.trim();
  return (
    <NodeShell color={chatColor ?? NODE_COLORS.LineItem} dashed={inferred}>
      <div className="flex items-center gap-1.5">
        <span className="font-medium">{str(p.product_code) || node.label}</span>
        <AgreementGlyph agreedBy={p.agreed_by} />
        {hasChildren && <ExpandCaret expanded={expanded} onToggle={onToggle} />}
      </div>
      <div className="text-[10px] text-muted-foreground">
        {qty} · {price} {str(p.incoterm)}
      </div>
      {inferred ? (
        <div className="mt-1">
          <InferredTag />
        </div>
      ) : null}
    </NodeShell>
  );
}

export function LineItemNode({ data }: GraphNodeProps) {
  const d = data as FlowNodeData;
  return (
    <>
      <Handle type="target" position={Position.Left} />
      <LineItemContent
        node={d.graphNode}
        expanded={d.expanded}
        hasChildren={d.hasChildren}
        onToggle={() => d.onToggle(d.graphNode.id)}
        chatColor={d.chatColor}
      />
      <Handle type="source" position={Position.Right} />
    </>
  );
}
