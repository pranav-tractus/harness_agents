import type { ComponentType } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { cn } from "@/lib/utils";
import type { ArchNode, NodeKind } from "@/architecture/types";

export type ArchFlowNodeData = {
  node: ArchNode;
  dimmed: boolean;
};

export const KIND_COLORS: Record<NodeKind, string> = {
  ui: "#0ea5e9",
  router: "#6366f1",
  service: "#8b5cf6",
  store: "#10b981",
  external: "#f59e0b",
  gate: "#f43f5e",
};

export const KIND_LABELS: Record<NodeKind, string> = {
  ui: "UI",
  router: "Route",
  service: "Service",
  store: "Store",
  external: "External",
  gate: "Gate",
};

function ArchNodeBody({ data }: NodeProps) {
  const { node, dimmed } = data as unknown as ArchFlowNodeData;
  const color = KIND_COLORS[node.kind];
  const isGate = node.kind === "gate";

  return (
    <>
      <Handle type="target" position={Position.Left} />
      <div
        className={cn(
          "min-w-[150px] max-w-[240px] rounded-md border bg-card px-3 py-2 text-xs shadow-sm transition-opacity",
          isGate && "border-dashed border-rose-400 bg-rose-50",
          dimmed && "opacity-25",
        )}
        style={{ borderLeft: `4px solid ${color}` }}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold text-foreground">{node.label}</span>
          <span
            className="shrink-0 rounded px-1 py-px text-[9px] font-medium uppercase tracking-wide text-white"
            style={{ backgroundColor: color }}
          >
            {KIND_LABELS[node.kind]}
          </span>
        </div>
        {node.anchor ? (
          <div className="mt-1 truncate font-mono text-[9px] text-muted-foreground">
            {node.anchor.split("::")[0].split("/").pop()}
          </div>
        ) : null}
        {node.invariant ? (
          <div className="mt-1 text-[9px] italic text-amber-600">invariant</div>
        ) : null}
      </div>
      <Handle type="source" position={Position.Right} />
    </>
  );
}

// Every kind shares one component; the visual difference is driven by node.kind
// inside ArchNodeBody. The registry stays keyed by kind so React Flow can look
// up a type name that matches the data.
export const archNodeTypes: Record<string, ComponentType<NodeProps>> = {
  ui: ArchNodeBody,
  router: ArchNodeBody,
  service: ArchNodeBody,
  store: ArchNodeBody,
  external: ArchNodeBody,
  gate: ArchNodeBody,
};
