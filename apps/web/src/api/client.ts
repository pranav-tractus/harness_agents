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
  name: string | null;
  short_description: string;
  long_description: string | null;
  spec: string | null;
  metadata: Record<string, string>;
  build_status?: string;
};
export type Message = {
  id: string;
  customer_id: string;
  chat_id: string;
  chat_status: string;
  seq: number;
  role: string;
  kind: string;
  body: string;
  summary_id: string | null;
  summary_json: string | null;
  created_at: string;
};
export type ModelOption = { key: string; display_name: string; provider: string };
export type AgentResult = { messages: Message[]; summary: unknown | null };
export type GraphNode = { id: string; label: string; type: string; properties: Record<string, unknown>; chat_id?: string };
export type GraphEdge = { id: string; source: string; target: string; type: string; properties: Record<string, unknown> };
export type GraphData = { nodes: GraphNode[]; edges: GraphEdge[] };
export type Slot = {
  slot: string; value: string | null; source: string;
  confidence: string; agreed_by: string[];
};

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
  createProduct: (payload: {
    code: string;
    name?: string | null;
    short_description: string;
    long_description?: string | null;
    spec?: string | null;
    metadata?: Record<string, string>;
  }) =>
    req<Product>("/api/products", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateProduct: (
    id: string,
    patch: {
      name?: string | null;
      short_description?: string | null;
      long_description?: string | null;
      spec?: string | null;
      metadata?: Record<string, string>;
    },
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
  postMessage: (id: string, role: string, body: string, model_key?: string) =>
    req<AgentResult>(`/api/customers/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ role, body, model_key }),
    }),
  listModels: () => req<ModelOption[]>("/api/models"),
  getGraphChat: (customerId: string) =>
    req<GraphData>(`/api/customers/${customerId}/graph`),
  getGraphProfile: (customerId: string) =>
    req<GraphData>(`/api/customers/${customerId}/graph`),
  getCustomerGraph: (customerId: string) =>
    req<GraphData>(`/api/customers/${customerId}/graph`),
  buildProduct: (code: string) =>
    req<Product>(`/api/products/${code}/build`, { method: "POST" }),
  getGraphProducts: () => req<GraphData>("/api/graph/products"),
};
