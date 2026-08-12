import { Navigate, Route, Routes } from "react-router";
import { RootLayout } from "@/components/RootLayout";
import { ArchitecturePage } from "@/pages/ArchitecturePage";
import { ChatPage } from "@/pages/ChatPage";
import { GraphsPage } from "@/pages/GraphsPage";
import { NotFound } from "@/pages/NotFound";
import { OrgsPage } from "@/pages/OrgsPage";
import { ProductsPage } from "@/pages/ProductsPage";
import { FirstCustomerRedirect } from "@/components/FirstCustomerRedirect";

export default function App() {
  return (
    <Routes>
      <Route element={<RootLayout />}>
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="chat" element={<FirstCustomerRedirect base="/chat" />} />
        <Route path="chat/:customerId" element={<ChatPage />} />
        <Route path="orgs" element={<OrgsPage />} />
        <Route path="orgs/:orgId/products" element={<ProductsPage />} />
        <Route path="products" element={<ProductsPage />} />
        <Route path="graphs" element={<FirstCustomerRedirect base="/graphs" />} />
        <Route path="graphs/:customerId" element={<GraphsPage />} />
        <Route path="architecture" element={<ArchitecturePage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
