import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { GraphCanvas } from "@/components/GraphCanvas";
import { GraphDetailPanel, type SelectedElement } from "@/components/GraphDetailPanel";
import { api, type Customer, type GraphData, type GraphEdge, type GraphNode } from "@/api/client";

type GraphTab = "chat" | "profile" | "products";

const EMPTY_GRAPH: GraphData = { nodes: [], edges: [] };

const EMPTY_SUBTITLES: Record<GraphTab, string> = {
  chat: "Run /create-sales-order in the chat to build this graph",
  profile: "Add customer profile details to populate this graph",
  products: "Add products in the Products tab to populate this graph",
};

export function GraphsPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>("");
  const [activeTab, setActiveTab] = useState<GraphTab>("chat");
  const [graphData, setGraphData] = useState<GraphData>(EMPTY_GRAPH);
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

  const loadGraph = useCallback(
    async (customerId: string, tab: GraphTab) => {
      try {
        let data: GraphData;
        if (tab === "chat") data = await api.getGraphChat(customerId);
        else if (tab === "profile") data = await api.getGraphProfile(customerId);
        else data = await api.getGraphProducts();
        setGraphData(data);
        setSelected(null);
      } catch {
        toast.error("Failed to load graph");
        setGraphData(EMPTY_GRAPH);
      }
    },
    [],
  );

  useEffect(() => {
    if (activeTab === "products") {
      loadGraph("", "products");
    } else if (selectedCustomerId) {
      loadGraph(selectedCustomerId, activeTab);
    }
  }, [selectedCustomerId, activeTab, loadGraph]);

  function handleTabChange(value: string) {
    setActiveTab(value as GraphTab);
    setSelected(null);
  }

  function handleSelectNode(node: GraphNode) {
    setSelected({ kind: "node", element: node });
  }

  function handleSelectEdge(edge: GraphEdge) {
    setSelected({ kind: "edge", element: edge });
  }

  return (
    <div className="flex flex-col" style={{ height: "calc(100vh - 3.5rem)" }}>
      <div className="flex items-center gap-4 px-6 py-3 border-b shrink-0">
        <Tabs value={activeTab} onValueChange={handleTabChange}>
          <TabsList>
            <TabsTrigger value="chat">Chat Graph</TabsTrigger>
            <TabsTrigger value="profile">Profile Graph</TabsTrigger>
            <TabsTrigger value="products">Product Catalog</TabsTrigger>
          </TabsList>
        </Tabs>
        {activeTab !== "products" && (
          <Select value={selectedCustomerId} onValueChange={setSelectedCustomerId}>
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
        )}
      </div>
      <div className="flex-1 min-h-0">
        <GraphCanvas
          data={graphData}
          emptySubtitle={EMPTY_SUBTITLES[activeTab]}
          onSelectNode={handleSelectNode}
          onSelectEdge={handleSelectEdge}
        />
      </div>
      <GraphDetailPanel selected={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
