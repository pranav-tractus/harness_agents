import { useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ChatPage } from "@/pages/ChatPage";
import { ProductsPage } from "@/pages/ProductsPage";
import { GraphsPage } from "@/pages/GraphsPage";
import { ArchitecturePage } from "@/pages/ArchitecturePage";

type GraphNav = { customerId: string; seq: number };

export default function App() {
  const [tab, setTab] = useState("chat");
  const [graphNav, setGraphNav] = useState<GraphNav | null>(null);

  function handleNavigateToMessage(customerId: string, seq: number) {
    setGraphNav({ customerId, seq });
    setTab("chat");
  }

  return (
    <div className="min-h-screen bg-background">
      <Tabs value={tab} onValueChange={(value) => value && setTab(value)} className="flex flex-col">
        <header className="flex h-14 items-center justify-between w-full bg-card border-b border-border px-6 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-primary text-[10px] font-bold text-primary-foreground select-none">
              CS
            </div>
            <span className="text-sm font-semibold text-foreground tracking-tight">Chat Simulation</span>
          </div>
          <TabsList variant="line" className="nav-tabs h-full gap-0 border-none bg-transparent p-0">
            <TabsTrigger value="chat" className="h-full rounded-none px-5 text-sm">Chat</TabsTrigger>
            <TabsTrigger value="products" className="h-full rounded-none px-5 text-sm">Products</TabsTrigger>
            <TabsTrigger value="graphs" className="h-full rounded-none px-5 text-sm">Graphs</TabsTrigger>
            <TabsTrigger value="architecture" className="h-full rounded-none px-5 text-sm">Architecture</TabsTrigger>
          </TabsList>
        </header>
        <main className="flex-1 overflow-hidden">
          <TabsContent value="chat" className="mt-0">
            <ChatPage focusMessage={graphNav} onFocusHandled={() => setGraphNav(null)} />
          </TabsContent>
          <TabsContent value="products" className="mt-0">
            <ProductsPage />
          </TabsContent>
          <TabsContent value="graphs" className="mt-0">
            <GraphsPage onNavigateToMessage={handleNavigateToMessage} />
          </TabsContent>
          <TabsContent value="architecture" className="mt-0">
            <ArchitecturePage />
          </TabsContent>
        </main>
      </Tabs>
      <Toaster />
    </div>
  );
}
