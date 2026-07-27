import { useCallback, useEffect, useMemo } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  useReactFlow,
  MarkerType,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "@dagrejs/dagre";
import { edgesForLayer, nodesForLayer } from "@/architecture/spec";
import type { ArchEdge, ArchNode, FlowId, LayerId } from "@/architecture/types";
import { archNodeTypes, KIND_COLORS, type ArchFlowNodeData } from "./nodeTypes";

const NODE_W = 210;
const NODE_H = 62;

function isDimmed(flows: FlowId[] | undefined, active: FlowId | null): boolean {
  if (!active) return false;
  return !flows || !flows.includes(active);
}

function edgeStyle(edge: ArchEdge, dimmed: boolean) {
  const gate = edge.kind === "gate-fail";
  return {
    stroke: gate ? "#f43f5e" : edge.kind === "data" ? "#10b981" : "#94a3b8",
    strokeWidth: gate ? 1.5 : 1.25,
    strokeDasharray: gate ? "5 4" : undefined,
    opacity: dimmed ? 0.15 : 1,
  };
}

function applyLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 45, ranksep: 110 });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    return { ...n, position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 } };
  });
}

function FitViewOnChange({ deps }: { deps: unknown }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const t = requestAnimationFrame(() => fitView({ duration: 200, padding: 0.15 }));
    return () => cancelAnimationFrame(t);
  }, [deps, fitView]);
  return null;
}

type Props = {
  layer: LayerId;
  activeFlow: FlowId | null;
  onSelectNode: (node: ArchNode) => void;
};

function ArchCanvasInner({ layer, activeFlow, onSelectNode }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const specNodes = useMemo(() => nodesForLayer(layer), [layer]);
  const specEdges = useMemo(() => edgesForLayer(layer), [layer]);

  useEffect(() => {
    const flowNodes: Node[] = specNodes.map((n) => ({
      id: n.id,
      type: n.kind,
      position: { x: 0, y: 0 },
      data: { node: n, dimmed: isDimmed(n.flows, activeFlow) } satisfies ArchFlowNodeData as unknown as Record<string, unknown>,
    }));

    const flowEdges: Edge[] = specEdges.map((e) => {
      const dimmed = isDimmed(e.flows, activeFlow);
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
        type: "smoothstep",
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
        style: edgeStyle(e, dimmed),
        labelStyle: { fontSize: 9, fill: "#94a3b8" },
        labelBgStyle: { fill: "#ffffff", fillOpacity: 0.85 },
      };
    });

    // Layout ignores the dim state so toggling a flow never moves a node —
    // the reader's spatial memory of the diagram survives every toggle.
    setNodes(applyLayout(flowNodes, flowEdges));
    setEdges(flowEdges);
  }, [specNodes, specEdges, activeFlow, setNodes, setEdges]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_, node) => onSelectNode((node.data as unknown as ArchFlowNodeData).node),
    [onSelectNode],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={archNodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={handleNodeClick}
      minZoom={0.2}
    >
      <FitViewOnChange deps={layer} />
      <MiniMap
        pannable
        zoomable
        nodeColor={(n) => KIND_COLORS[(n.data as unknown as ArchFlowNodeData).node.kind]}
      />
      <Controls />
      <Background variant={BackgroundVariant.Dots} />
    </ReactFlow>
  );
}

export function ArchCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <ArchCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
