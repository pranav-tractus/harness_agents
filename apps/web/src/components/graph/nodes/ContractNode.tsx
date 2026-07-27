import { Handle, Position } from "@xyflow/react";
import type { GraphNode } from "@/api/client";
import { ExpandCaret, NODE_COLORS, NodeShell, contractGlyph } from "./parts";
import type { FlowNodeData, GraphNodeProps, NodeCounts } from "./types";

function str(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}

export function ContractContent({
  node,
  expanded,
  hasChildren,
  onToggle,
  chatColor,
  counts,
}: {
  node: GraphNode;
  expanded: boolean;
  hasChildren: boolean;
  onToggle: () => void;
  chatColor?: string;
  counts?: NodeCounts;
}) {
  const p = node.properties;
  const finalized = str(p.status) === "finalized";
  return (
    <NodeShell color={chatColor ?? NODE_COLORS.Contract}>
      <div className="flex items-center gap-1.5">
        <span className="font-semibold">rev {str(p.revision)}</span>
        <span className="text-[10px] text-muted-foreground">
          {counts?.lines ?? 0} lines
        </span>
        {hasChildren && <ExpandCaret expanded={expanded} onToggle={onToggle} />}
      </div>
      <div className={finalized ? "text-[10px] text-emerald-600" : "text-[10px] text-amber-600"}>
        {contractGlyph(str(p.status))}
      </div>
    </NodeShell>
  );
}

export function ContractNode({ data }: GraphNodeProps) {
  const d = data as FlowNodeData;
  return (
    <>
      <Handle type="target" position={Position.Left} />
      <ContractContent
        node={d.graphNode}
        expanded={d.expanded}
        hasChildren={d.hasChildren}
        onToggle={() => d.onToggle(d.graphNode.id)}
        chatColor={d.chatColor}
        counts={d.counts}
      />
      <Handle type="source" position={Position.Right} />
    </>
  );
}
