import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, type Customer, type Message, type Slot } from "@/api/client";
import { ChatPane } from "@/components/ChatPane";
import { CustomerDetails } from "@/components/CustomerDetails";
import { CustomerSidebar } from "@/components/CustomerSidebar";
import { MessageComposer } from "@/components/MessageComposer";
import { ModelPicker } from "@/components/ModelPicker";

type PendingSummary = {
  id?: string;
  status?: string;
  slots?: Slot[];
};

function pendingFromMessages(rows: Message[]): PendingSummary | null {
  for (let i = rows.length - 1; i >= 0; i--) {
    const m = rows[i];
    if (m.kind === "final") return null;
    if (m.kind === "draft" && m.summary_id) {
      return { id: m.summary_id, status: "pending", slots: [] };
    }
  }
  return null;
}

function showApprove(pending: PendingSummary | null): boolean {
  if (!pending || pending.status !== "pending") return false;
  const slots = pending.slots;
  if (!slots || slots.length === 0) return true;
  return slots.some(
    (s) => !s.agreed_by.includes("seller") || !s.agreed_by.includes("customer"),
  );
}

type Props = {
  focusMessage?: { customerId: string; seq: number } | null;
  onFocusHandled?: () => void;
};

export function ChatPage({ focusMessage, onFocusHandled }: Props) {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [modelKey, setModelKey] = useState("sonnet-4-6");
  const [role, setRole] = useState<"seller" | "customer">("seller");
  const [pendingSummary, setPendingSummary] = useState<PendingSummary | null>(null);
  const [scrollToSeq, setScrollToSeq] = useState<number | null>(null);
  const [loadedMessagesCustomerId, setLoadedMessagesCustomerId] = useState<string | null>(null);

  const selectedCustomer = customers.find((c) => c.id === selectedId) ?? null;

  const loadMessages = useCallback(async (customerId: string) => {
    const rows = await api.listMessages(customerId);
    setMessages(rows);
    setLoadedMessagesCustomerId(customerId);
    setPendingSummary(pendingFromMessages(rows));
  }, []);

  const loadCustomers = useCallback(async () => {
    const rows = await api.listCustomers();
    setCustomers(rows);
    return rows;
  }, []);

  useEffect(() => {
    loadCustomers()
      .then((rows) => {
        if (rows.length > 0) setSelectedId((current) => current || rows[0].id);
      })
      .catch(console.error);
  }, [loadCustomers]);

  useEffect(() => {
    if (selectedId) {
      loadMessages(selectedId).catch(console.error);
    }
  }, [selectedId, loadMessages]);

  useEffect(() => {
    if (focusMessage) setSelectedId(focusMessage.customerId);
  }, [focusMessage]);

  useEffect(() => {
    setScrollToSeq(null);
  }, [selectedId]);

  useEffect(() => {
    if (scrollToSeq == null) return;
    const timer = setTimeout(() => setScrollToSeq(null), 1800);
    return () => clearTimeout(timer);
  }, [scrollToSeq]);

  useEffect(() => {
    if (!focusMessage) return;
    if (loadedMessagesCustomerId !== focusMessage.customerId) return;
    if (messages.length === 0) {
      toast.error("Message not found");
      onFocusHandled?.();
      return;
    }
    const found = messages.some((m) => m.seq === focusMessage.seq);
    if (found) setScrollToSeq(focusMessage.seq);
    else toast.error("Message not found");
    onFocusHandled?.();
  }, [focusMessage, messages, loadedMessagesCustomerId, onFocusHandled]);

  async function handleMessage(body: string) {
    if (!selectedId) return;
    try {
      await api.postMessage(selectedId, role, body);
      await loadMessages(selectedId);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to send message");
    }
  }

  async function handleAskAgent() {
    if (!selectedId) return;
    try {
      const result = await api.invokeAgent(selectedId, modelKey, "ask");
      if (result.summary) setPendingSummary(result.summary as PendingSummary);
      await loadMessages(selectedId);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Agent unavailable");
    }
  }

  async function handleApprove() {
    if (!selectedId) return;
    try {
      await api.invokeAgent(selectedId, modelKey, "approve");
      setPendingSummary(null);
      await loadMessages(selectedId);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Approve failed");
    }
  }

  function handleCustomerUpdated(updated: Customer) {
    setCustomers((rows) => rows.map((c) => (c.id === updated.id ? updated : c)));
  }

  async function handleAddCustomer(name: string) {
    try {
      const created = await api.createCustomer(name);
      await loadCustomers();
      setSelectedId(created.id);
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
        setSelectedId(rows.length > 0 ? rows[0].id : "");
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
        onSelect={setSelectedId}
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
        <ChatPane key={selectedId} messages={messages} scrollToSeq={scrollToSeq} />
        <MessageComposer
          role={role}
          onRoleChange={setRole}
          onMessage={handleMessage}
          onAskAgent={handleAskAgent}
          onApprove={handleApprove}
          showApprove={showApprove(pendingSummary)}
        />
      </div>
      <CustomerDetails customer={selectedCustomer} onUpdated={handleCustomerUpdated} />
    </div>
  );
}
