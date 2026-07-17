import { useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ChatPage } from "@/pages/ChatPage";
import { ProductsPage } from "@/pages/ProductsPage";
import { GraphsPage } from "@/pages/GraphsPage";

export default function App() {
  const [tab, setTab] = useState("chat");

  return (
    <div className="min-h-screen bg-background">
      <Tabs value={tab} onValueChange={(value) => value && setTab(value)} className="flex flex-col">
        <header className="flex items-center justify-between max-w-7xl w-full mx-auto bg-card px-6 py-2">
          <div className="flex items-center gap-2.5">
            <h1 className="text-sm font-semibold tracking-tight">Chat Simulation</h1>
          </div>
          <div className="">
            <TabsList>
              <TabsTrigger value="chat">Chat</TabsTrigger>
              <TabsTrigger value="products">Products</TabsTrigger>
              <TabsTrigger value="graphs">Graphs</TabsTrigger>
            </TabsList>
          </div>
        </header>
        <main className="flex-1 overflow-hidden border-t">
          <TabsContent value="chat" className="mt-0">
            <ChatPage />
          </TabsContent>
          <TabsContent value="products" className="mt-0">
            <ProductsPage />
          </TabsContent>
          <TabsContent value="graphs" className="mt-0">
            <GraphsPage />
          </TabsContent>
        </main>
      </Tabs>
      <Toaster />
    </div>
  );
}
