import { useCallback, useEffect, useMemo } from "react";
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
import { childrenMap, computeVisibleNodeIds, rootIds } from "@/components/graph/hierarchy";
import { nodeTypes, type FlowNodeData, type NodeCounts } from "@/components/graph/nodes";

const NODE_SIZES: Record<string, { w: number; h: number }> = {
  Customer: { w: 190, h: 56 },
  Chat: { w: 190, h: 52 },
  Contract: { w: 180, h: 56 },
  LineItem: { w: 230, h: 60 },
  Term: { w: 200, h: 52 },
  Product: { w: 200, h: 52 },
  Port: { w: 150, h: 40 },
  MessageRef: { w: 210, h: 52 },
  Attribute: { w: 190, h: 40 },
  Preference: { w: 200, h: 40 },
};
const DEFAULT_SIZE = { w: 180, h: 48 };

function sizeOf(type: string) {
  return NODE_SIZES[type] ?? DEFAULT_SIZE;
}

function countsByNode(nodes: GraphNode[], edges: GraphEdge[]): Map<string, NodeCounts> {
  const out = new Map<string, NodeCounts>();
  const totalContracts = nodes.filter((n) => n.type === "Contract").length;
  for (const n of nodes) {
    if (n.type === "Customer") {
      out.set(n.id, {
        chats: edges.filter((e) => e.type === "HAS_CHAT" && e.source === n.id).length,
        contracts: totalContracts,
      });
    } else if (n.type === "Contract") {
      out.set(n.id, {
        lines: edges.filter((e) => e.type === "HAS_LINE" && e.source === n.id).length,
        terms: edges.filter((e) => e.type === "HAS_TERM" && e.source === n.id).length,
      });
    }
  }
  return out;
}

function toFlowEdges(gedges: GraphEdge[]): Edge[] {
  return gedges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.type,
    data: { graphEdge: e },
    type: "smoothstep",
    style: { stroke: e.type === "SUPERSEDES" ? "#f43f5e" : "#cbd5e1" },
    labelStyle: { fontSize: 9, fill: "#94a3b8" },
  }));
}

function applyLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 90 });
  nodes.forEach((n) => {
    const s = sizeOf((n.data as FlowNodeData).graphNode.type);
    g.setNode(n.id, { width: s.w, height: s.h });
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    const s = sizeOf((n.data as FlowNodeData).graphNode.type);
    return { ...n, position: { x: pos.x - s.w / 2, y: pos.y - s.h / 2 } };
  });
}

type Props = {
  data: GraphData;
  emptySubtitle: string;
  expanded: Set<string>;
  onToggleExpand: (id: string) => void;
  chatColors: Record<string, string>;
  onSelectNode: (node: GraphNode) => void;
  onSelectEdge: (edge: GraphEdge) => void;
};

export function GraphCanvas({
  data,
  emptySubtitle,
  expanded,
  onToggleExpand,
  chatColors,
  onSelectNode,
  onSelectEdge,
}: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const visible = useMemo(
    () => computeVisibleNodeIds(data.nodes, data.edges, expanded),
    [data, expanded],
  );

  useEffect(() => {
    const roots = rootIds(data.nodes, data.edges);
    const kids = childrenMap(data.edges);
    const counts = countsByNode(data.nodes, data.edges);

    const flowNodes: Node[] = data.nodes
      .filter((n) => visible.has(n.id))
      .map((n) => ({
        id: n.id,
        type: n.type,
        position: { x: 0, y: 0 },
        data: {
          graphNode: n,
          expanded: expanded.has(n.id),
          hasChildren: (kids.get(n.id)?.length ?? 0) > 0 && !roots.has(n.id),
          onToggle: onToggleExpand,
          chatColor: n.chat_id ? chatColors[n.chat_id] : undefined,
          counts: counts.get(n.id),
        } satisfies FlowNodeData,
      }));

    const flowEdges = toFlowEdges(
      data.edges.filter((e) => visible.has(e.source) && visible.has(e.target)),
    );

    setNodes(applyLayout(flowNodes, flowEdges));
    setEdges(flowEdges);
  }, [data, visible, expanded, chatColors, onToggleExpand, setNodes, setEdges]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_, node) => onSelectNode((node.data as FlowNodeData).graphNode),
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
      nodeTypes={nodeTypes}
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
