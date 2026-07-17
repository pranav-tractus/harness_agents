import { useCallback, useEffect } from "react";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeMouseHandler,
  type EdgeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "@dagrejs/dagre";
import type { GraphData, GraphEdge, GraphNode } from "@/api/client";

const NODE_COLORS: Record<string, string> = {
  Customer: "#6366f1",
  Product: "#10b981",
  Port: "#f59e0b",
  Episode: "#64748b",
  Attribute: "#8b5cf6",
  Alias: "#0ea5e9",
  SpecAttr: "#f43f5e",
};

const NODE_W = 160;
const NODE_H = 40;

function toFlowNodes(gnodes: GraphNode[]): Node[] {
  return gnodes.map((n) => ({
    id: n.id,
    data: { label: n.label, graphNode: n },
    position: { x: 0, y: 0 },
    style: {
      background: NODE_COLORS[n.type] ?? "#94a3b8",
      color: "#fff",
      borderRadius: 6,
      border: "none",
      fontSize: 12,
      width: NODE_W,
    },
  }));
}

function toFlowEdges(gedges: GraphEdge[]): Edge[] {
  return gedges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.type,
    data: { graphEdge: e },
    type: "smoothstep",
    style: { stroke: "#94a3b8" },
    labelStyle: { fontSize: 10, fill: "#64748b" },
  }));
}

function applyLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 50, ranksep: 100 });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    return { ...n, position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 } };
  });
}

type Props = {
  data: GraphData;
  emptySubtitle: string;
  onSelectNode: (node: GraphNode) => void;
  onSelectEdge: (edge: GraphEdge) => void;
};

export function GraphCanvas({ data, emptySubtitle, onSelectNode, onSelectEdge }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    const fn = toFlowNodes(data.nodes);
    const fe = toFlowEdges(data.edges);
    setNodes(applyLayout(fn, fe));
    setEdges(fe);
  }, [data, setNodes, setEdges]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_, node) => onSelectNode((node.data as { graphNode: GraphNode }).graphNode),
    [onSelectNode],
  );

  const handleEdgeClick: EdgeMouseHandler = useCallback(
    (_, edge) => onSelectEdge((edge.data as { graphEdge: GraphEdge }).graphEdge),
    [onSelectEdge],
  );

  if (data.nodes.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
        <p className="text-sm font-medium">No graph data yet</p>
        <p className="text-xs">{emptySubtitle}</p>
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={handleNodeClick}
      onEdgeClick={handleEdgeClick}
      fitView
    >
      <MiniMap />
      <Controls />
      <Background variant={BackgroundVariant.Dots} />
    </ReactFlow>
  );
}
