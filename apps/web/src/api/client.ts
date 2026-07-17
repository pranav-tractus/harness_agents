export type Customer = {
  id: string;
  name: string;
  profile: Profile;
  last_contract_seq: number;
};
export type Profile = {
  email: string | null;
  phone: string | null;
  business_address: string | null;
  delivery_address: string | null;
  contact_point: string | null;
  approved_credit_term: string | null;
  approved_white_label: string | null;
  latest_packing_and_loading: string | null;
};
export type Product = {
  id: string;
  code: string;
  description: string;
  spec: string | null;
};
export type Message = {
  id: string;
  customer_id: string;
  seq: number;
  role: string;
  kind: string;
  body: string;
  summary_id: string | null;
  summary_json: string | null;
  created_at: string;
};
export type ModelOption = { key: string; display_name: string; provider: string };
export type CommandResult = { messages: Message[]; summary: unknown | null };
export type GraphNode = { id: string; label: string; type: string; properties: Record<string, unknown> };
export type GraphEdge = { id: string; source: string; target: string; type: string; properties: Record<string, unknown> };
export type GraphData = { nodes: GraphNode[]; edges: GraphEdge[] };

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json() as Promise<T>;
}

export const api = {
  listCustomers: () => req<Customer[]>("/api/customers"),
  getCustomer: (id: string) => req<Customer>(`/api/customers/${id}`),
  createCustomer: (name: string) =>
    req<Customer>("/api/customers", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  deleteCustomer: (id: string) =>
    fetch(`/api/customers/${id}`, { method: "DELETE" }).then((r) => {
      if (!r.ok) throw new Error(`${r.status} delete customer`);
    }),
  updateProfile: (id: string, profile: Profile) =>
    req<Customer>(`/api/customers/${id}`, {
      method: "PUT",
      body: JSON.stringify({ profile }),
    }),
  listProducts: () => req<Product[]>("/api/products"),
  createProduct: (payload: { code: string; description: string; spec: string | null }) =>
    req<Product>("/api/products", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateProduct: (
    id: string,
    patch: { description?: string | null; spec?: string | null },
  ) =>
    req<Product>(`/api/products/${id}`, {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  deleteProduct: (id: string) =>
    fetch(`/api/products/${id}`, { method: "DELETE" }).then((r) => {
      if (!r.ok) throw new Error(`${r.status} delete product`);
    }),
  listMessages: (id: string) => req<Message[]>(`/api/customers/${id}/messages`),
  postMessage: (id: string, role: string, body: string) =>
    req<Message>(`/api/customers/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ role, body }),
    }),
  runCommand: (id: string, command: string, args: string | null, model_key: string) =>
    req<CommandResult>(`/api/customers/${id}/commands`, {
      method: "POST",
      body: JSON.stringify({ command, args, model_key }),
    }),
  listModels: () => req<ModelOption[]>("/api/models"),
  getGraphChat: (customerId: string) =>
    req<GraphData>(`/api/customers/${customerId}/graph/chat`),
  getGraphProfile: (customerId: string) =>
    req<GraphData>(`/api/customers/${customerId}/graph/profile`),
  getGraphProducts: () => req<GraphData>("/api/graph/products"),
};
