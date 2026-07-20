import { Handle, Position } from "@xyflow/react";
import type { GraphNode } from "@/api/client";
import { ChatStatusChip, ExpandCaret, NODE_COLORS, NodeShell } from "./parts";
import type { FlowNodeData, GraphNodeProps } from "./types";

function str(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}

export function BranchContent({
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
  const date = str(p.created_at) || str(p.date);
  return (
    <NodeShell color={chatColor ?? NODE_COLORS.Chat}>
      <div className="flex items-center gap-1.5">
        <span className="font-semibold">{node.label}</span>
        <ChatStatusChip status={str(p.status) || undefined} />
        {hasChildren && <ExpandCaret expanded={expanded} onToggle={onToggle} />}
      </div>
      {date ? <div className="text-[10px] text-muted-foreground">{date}</div> : null}
    </NodeShell>
  );
}

export function BranchNode({ data }: GraphNodeProps) {
  const d = data as FlowNodeData;
  return (
    <>
      <Handle type="target" position={Position.Left} />
      <BranchContent
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
