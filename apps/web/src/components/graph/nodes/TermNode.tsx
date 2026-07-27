import { Handle, Position } from "@xyflow/react";
import type { GraphNode } from "@/api/client";
import { AgreementGlyph, InferredTag, NODE_COLORS, NodeShell, isInferred } from "./parts";
import type { FlowNodeData, GraphNodeProps } from "./types";

function str(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}

export function TermContent({ node, chatColor }: { node: GraphNode; chatColor?: string }) {
  const p = node.properties;
  const inferred = isInferred(node);
  return (
    <NodeShell color={chatColor ?? NODE_COLORS.Term} dashed={inferred}>
      <div className="flex items-center gap-1.5">
        <span className="font-medium">{str(p.kind)}</span>
        <span>{str(p.value)}</span>
        <AgreementGlyph agreedBy={p.agreed_by} />
      </div>
      {inferred ? (
        <div className="mt-1">
          <InferredTag />
        </div>
      ) : null}
    </NodeShell>
  );
}

export function TermNode({ data }: GraphNodeProps) {
  const d = data as FlowNodeData;
  return (
    <>
      <Handle type="target" position={Position.Left} />
      <TermContent node={d.graphNode} chatColor={d.chatColor} />
      <Handle type="source" position={Position.Right} />
    </>
  );
}
