import { Handle, Position } from "@xyflow/react";
import type { GraphNode } from "@/api/client";
import { BuildBadge, NODE_COLORS, NodeShell } from "./parts";
import type { FlowNodeData, GraphNodeProps, NodeCounts } from "./types";

function str(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}

export function LeafContent({ node, counts }: { node: GraphNode; counts?: NodeCounts }) {
  const p = node.properties;
  const color = node.chat_id ? undefined : NODE_COLORS[node.type];

  if (node.type === "Customer") {
    return (
      <NodeShell color={NODE_COLORS.Customer}>
        <div className="font-semibold">{node.label}</div>
        <div className="text-[10px] text-muted-foreground">
          {counts?.chats ?? 0} chats · {counts?.contracts ?? 0} contracts
        </div>
      </NodeShell>
    );
  }

  if (node.type === "Product") {
    const build = str(p.build_status);
    return (
      <NodeShell color={NODE_COLORS.Product}>
        <div className="flex items-center gap-1.5">
          <span className="font-medium">{str(p.code) || node.label}</span>
          {build && <BuildBadge status={build} />}
        </div>
        {p.description ? (
          <div className="text-[10px] text-muted-foreground truncate max-w-[180px]">
            {str(p.description)}
          </div>
        ) : null}
      </NodeShell>
    );
  }

  if (node.type === "MessageRef") {
    return (
      <NodeShell color={NODE_COLORS.MessageRef}>
        <div className="font-medium">
          #{str(p.seq)} {str(p.role)}
        </div>
        {p.snippet ? (
          <div className="text-[10px] text-muted-foreground truncate max-w-[180px]">
            {str(p.snippet)}
          </div>
        ) : null}
      </NodeShell>
    );
  }

  if (node.type === "Attribute") {
    return (
      <NodeShell color={NODE_COLORS.Attribute}>
        <div>
          <span className="font-medium">{str(p.key)}</span>: {str(p.value)}
        </div>
      </NodeShell>
    );
  }

  if (node.type === "Preference") {
    const support = p.support !== undefined && p.support !== null ? ` ×${str(p.support)}` : "";
    return (
      <NodeShell color={NODE_COLORS.Preference}>
        <div>
          <span className="font-medium">{str(p.slot)}</span> = {str(p.value)}
          <span className="text-muted-foreground">{support}</span>
        </div>
      </NodeShell>
    );
  }

  // Port and any other leaf: name/label.
  return (
    <NodeShell color={color ?? NODE_COLORS[node.type]}>
      <div className="font-medium">{str(p.name) || node.label}</div>
    </NodeShell>
  );
}

export function LeafNode({ data }: GraphNodeProps) {
  const d = data as FlowNodeData;
  return (
    <>
      <Handle type="target" position={Position.Left} />
      <LeafContent node={d.graphNode} counts={d.counts} />
      <Handle type="source" position={Position.Right} />
    </>
  );
}
