import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { api, type Customer, type Message } from "@/api/client";
import { ChatPane } from "@/components/ChatPane";
import { CustomerDetails } from "@/components/CustomerDetails";
import { CustomerSidebar } from "@/components/CustomerSidebar";
import { MessageComposer } from "@/components/MessageComposer";
import { ModelPicker } from "@/components/ModelPicker";

export function ChatPage() {
  const { customerId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const selectedId = customerId;
  const focusSeq = searchParams.get("seq");

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [modelKey, setModelKey] = useState("sonnet-4-6");
  const [role, setRole] = useState<"seller" | "customer">("seller");
  const [scrollToSeq, setScrollToSeq] = useState<number | null>(null);
  const [loadedMessagesCustomerId, setLoadedMessagesCustomerId] = useState<string | null>(null);
  const [isAgentThinking, setIsAgentThinking] = useState(false);

  const selectedCustomer = customers.find((c) => c.id === selectedId) ?? null;

  const loadMessages = useCallback(async (cid: string) => {
    const rows = await api.listMessages(cid);
    setMessages(rows);
    setLoadedMessagesCustomerId(cid);
  }, []);

  const loadCustomers = useCallback(async () => {
    const rows = await api.listCustomers();
    setCustomers(rows);
    return rows;
  }, []);

  useEffect(() => {
    loadCustomers().catch(console.error);
  }, [loadCustomers]);

  useEffect(() => {
    if (selectedId) {
      loadMessages(selectedId).catch(console.error);
    }
  }, [selectedId, loadMessages]);

  useEffect(() => {
    setScrollToSeq(null);
  }, [selectedId]);

  useEffect(() => {
    if (scrollToSeq == null) return;
    const timer = setTimeout(() => setScrollToSeq(null), 1800);
    return () => clearTimeout(timer);
  }, [scrollToSeq]);

  useEffect(() => {
    if (focusSeq == null) return;
    if (loadedMessagesCustomerId !== selectedId) return;
    const seq = Number(focusSeq);
    if (messages.some((m) => m.seq === seq)) setScrollToSeq(seq);
    else toast.error("Message not found");
    setSearchParams({}, { replace: true });
  }, [focusSeq, messages, loadedMessagesCustomerId, selectedId, setSearchParams]);

  async function handleMessage(body: string) {
    if (!selectedId) return;
    setIsAgentThinking(true);
    try {
      await api.postMessage(selectedId, role, body, modelKey);
      await loadMessages(selectedId);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to send message");
    } finally {
      setIsAgentThinking(false);
    }
  }

  function handleCustomerUpdated(updated: Customer) {
    setCustomers((rows) => rows.map((c) => (c.id === updated.id ? updated : c)));
  }

  async function handleAddCustomer(name: string) {
    try {
      const created = await api.createCustomer(name);
      await loadCustomers();
      navigate(`/chat/${created.id}`);
      toast.success(`Added ${created.name}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add customer");
    }
  }

  async function handleDeleteCustomer(id: string) {
    try {
      await api.deleteCustomer(id);
      const rows = await loadCustomers();
      if (id === selectedId) {
        navigate(rows.length > 0 ? `/chat/${rows[0].id}` : "/chat");
        if (rows.length === 0) {
          setMessages([]);
          setLoadedMessagesCustomerId(null);
        }
      }
      toast.success("Customer deleted");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete customer");
    }
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      <CustomerSidebar
        customers={customers}
        selectedId={selectedId}
        onSelect={(id) => navigate(`/chat/${id}`)}
        onAdd={handleAddCustomer}
        onDelete={handleDeleteCustomer}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b px-4 py-2">
          <h1 className="text-lg font-semibold">
            {selectedCustomer?.name ?? "Chat Simulation"}
          </h1>
          <ModelPicker value={modelKey} onChange={setModelKey} />
        </div>
        <ChatPane key={selectedId} messages={messages} scrollToSeq={scrollToSeq} isAgentThinking={isAgentThinking} />
        <MessageComposer role={role} onRoleChange={setRole} onMessage={handleMessage} />
      </div>
      <CustomerDetails customer={selectedCustomer} onUpdated={handleCustomerUpdated} />
    </div>
  );
}
