import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { GraphCanvas } from "@/components/GraphCanvas";
import { GraphDetailPanel, type SelectedElement } from "@/components/GraphDetailPanel";
import { GraphLegend } from "@/components/GraphLegend";
import { assignChatColors } from "@/components/graph/hierarchy";
import { api, type Customer, type GraphData, type GraphEdge, type GraphNode } from "@/api/client";

const EMPTY_GRAPH: GraphData = { nodes: [], edges: [] };

type Props = {
  onNavigateToMessage?: (customerId: string, seq: number) => void;
};

export function GraphsPage({ onNavigateToMessage }: Props) {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>("");
  const [chatFilter, setChatFilter] = useState<string>("all");
  const [graphData, setGraphData] = useState<GraphData>(EMPTY_GRAPH);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<SelectedElement>(null);

  useEffect(() => {
    api
      .listCustomers()
      .then((rows) => {
        setCustomers(rows);
        if (rows.length > 0) setSelectedCustomerId((curr) => curr || rows[0].id);
      })
      .catch(console.error);
  }, []);

  const loadGraph = useCallback(async (customerId: string) => {
    try {
      const data = await api.getCustomerGraph(customerId);
      setGraphData(data);
      setSelected(null);
      setExpanded(new Set());
      setChatFilter("all");
    } catch {
      toast.error("Failed to load graph");
      setGraphData(EMPTY_GRAPH);
    }
  }, []);

  useEffect(() => {
    if (selectedCustomerId) loadGraph(selectedCustomerId);
  }, [selectedCustomerId, loadGraph]);

  const chatOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const n of graphData.nodes) {
      if (n.type === "Chat") seen.set(String(n.properties.id ?? n.id), n.label);
    }
    return Array.from(seen.entries()).map(([id, label]) => ({ id, label }));
  }, [graphData]);

  const chatColors = useMemo(
    () => assignChatColors(graphData.nodes.map((n) => n.chat_id).filter((c): c is string => !!c)),
    [graphData],
  );

  const displayedGraph = useMemo<GraphData>(() => {
    if (chatFilter === "all") return graphData;
    const nodes = graphData.nodes.filter((n) => !n.chat_id || n.chat_id === chatFilter);
    const ids = new Set(nodes.map((n) => n.id));
    const edges = graphData.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    return { nodes, edges };
  }, [chatFilter, graphData]);

  const handleToggleExpand = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  function handleChatFilter(value: string) {
    setChatFilter(value);
    if (value !== "all") {
      const chatNodeId = `Chat::${value}`;
      setExpanded((prev) => new Set(prev).add(chatNodeId));
    }
  }

  function handleSelectNode(node: GraphNode) {
    setSelected({ kind: "node", element: node });
  }
  function handleSelectEdge(edge: GraphEdge) {
    setSelected({ kind: "edge", element: edge });
  }

  function handleRefresh() {
    if (selectedCustomerId) loadGraph(selectedCustomerId);
  }

  return (
    <div className="flex flex-col" style={{ height: "calc(100vh - 3.5rem)" }}>
      <div className="flex items-center gap-4 border-b px-6 py-3 shrink-0">
        <Select value={selectedCustomerId} onValueChange={(v) => v && setSelectedCustomerId(v)}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Select customer" />
          </SelectTrigger>
          <SelectContent>
            {customers.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={chatFilter} onValueChange={(v) => v && handleChatFilter(v)}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Chat" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All chats</SelectItem>
            {chatOptions.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button variant="outline" size="sm" className="ml-auto" onClick={handleRefresh}>
          Refresh
        </Button>
      </div>

      <div className="relative min-h-0 flex-1">
        <GraphCanvas
          data={displayedGraph}
          emptySubtitle="Run the sales-order agent in the chat to build this graph"
          expanded={expanded}
          onToggleExpand={handleToggleExpand}
          chatColors={chatColors}
          onSelectNode={handleSelectNode}
          onSelectEdge={handleSelectEdge}
        />
        <GraphLegend />
      </div>

      <GraphDetailPanel
        selected={selected}
        graph={graphData}
        onClose={() => setSelected(null)}
        onNavigateToMessage={(seq) => onNavigateToMessage?.(selectedCustomerId, seq)}
      />
    </div>
  );
}
