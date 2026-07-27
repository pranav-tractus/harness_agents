import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GraphCanvas } from "@/components/GraphCanvas";
import { GraphDetailPanel, type SelectedElement } from "@/components/GraphDetailPanel";
import { GraphLegend } from "@/components/GraphLegend";
import { assignChatColors } from "@/components/graph/hierarchy";
import { api, type Customer, type GraphData, type GraphEdge, type GraphNode } from "@/api/client";

type GraphView = "customer" | "products";

const EMPTY_GRAPH: GraphData = { nodes: [], edges: [] };

const EMPTY_SUBTITLES: Record<GraphView, string> = {
  customer: "Run the sales-order agent in the chat to build this graph",
  products: "Add and build products in the Products tab to populate this graph",
};

type Props = {
  onNavigateToMessage?: (customerId: string, seq: number) => void;
};

export function GraphsPage({ onNavigateToMessage }: Props) {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>("");
  const [view, setView] = useState<GraphView>("customer");
  const [chatFilter, setChatFilter] = useState<string>("all");
  const [graphData, setGraphData] = useState<GraphData>(EMPTY_GRAPH);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<SelectedElement>(null);
  const [rebuilding, setRebuilding] = useState(false);

  useEffect(() => {
    api
      .listCustomers()
      .then((rows) => {
        setCustomers(rows);
        if (rows.length > 0) setSelectedCustomerId((curr) => curr || rows[0].id);
      })
      .catch(console.error);
  }, []);

  const loadGraph = useCallback(async (v: GraphView, customerId: string) => {
    try {
      let data: GraphData;
      if (v === "products") {
        const [graph, products] = await Promise.all([api.getGraphProducts(), api.listProducts()]);
        const byCode = new Map(products.map((p) => [p.code, p.build_status ?? "not built"]));
        data = {
          nodes: graph.nodes.map((n) =>
            n.type === "Product"
              ? { ...n, properties: { ...n.properties, build_status: byCode.get(String(n.properties.code)) ?? "not built" } }
              : n,
          ),
          edges: graph.edges,
        };
      } else {
        data = await api.getCustomerGraph(customerId);
      }
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
    if (view === "products") loadGraph("products", "");
    else if (selectedCustomerId) loadGraph("customer", selectedCustomerId);
  }, [view, selectedCustomerId, loadGraph]);

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

  // Chat filter: "all" shows every branch (collapsed); a specific chat keeps
  // only that branch's nodes (root nodes without a chat_id always shown).
  const displayedGraph = useMemo<GraphData>(() => {
    if (view !== "customer" || chatFilter === "all") return graphData;
    const nodes = graphData.nodes.filter((n) => !n.chat_id || n.chat_id === chatFilter);
    const ids = new Set(nodes.map((n) => n.id));
    const edges = graphData.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    return { nodes, edges };
  }, [view, chatFilter, graphData]);

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
    if (view === "products") loadGraph("products", "");
    else if (selectedCustomerId) loadGraph("customer", selectedCustomerId);
  }

  async function handleRebuild(code: string) {
    setRebuilding(true);
    try {
      await api.buildProduct(code);
      await loadGraph("products", "");
      toast.success(`Rebuilt ${code}`);
    } catch {
      toast.error("Build failed");
    } finally {
      setRebuilding(false);
    }
  }

  return (
    <div className="flex flex-col" style={{ height: "calc(100vh - 3.5rem)" }}>
      <div className="flex items-center gap-4 border-b px-6 py-3 shrink-0">
        <Tabs value={view} onValueChange={(v) => v && setView(v as GraphView)}>
          <TabsList>
            <TabsTrigger value="customer">Customer</TabsTrigger>
            <TabsTrigger value="products">Products</TabsTrigger>
          </TabsList>
        </Tabs>

        {view === "customer" && (
          <>
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
          </>
        )}

        <Button variant="outline" size="sm" className="ml-auto" onClick={handleRefresh}>
          Refresh
        </Button>
      </div>

      <div className="relative min-h-0 flex-1">
        <GraphCanvas
          data={displayedGraph}
          emptySubtitle={EMPTY_SUBTITLES[view]}
          expanded={expanded}
          onToggleExpand={handleToggleExpand}
          chatColors={chatColors}
          onSelectNode={handleSelectNode}
          onSelectEdge={handleSelectEdge}
        />
        <GraphLegend view={view} />
      </div>

      <GraphDetailPanel
        selected={selected}
        graph={graphData}
        onClose={() => setSelected(null)}
        onNavigateToMessage={(seq) => onNavigateToMessage?.(selectedCustomerId, seq)}
        onRebuild={handleRebuild}
        rebuilding={rebuilding}
      />
    </div>
  );
}
