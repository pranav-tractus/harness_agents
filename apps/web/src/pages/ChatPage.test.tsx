import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/client", () => {
  const customers = [
    { id: "c1", name: "Acme", profile: {}, last_contract_seq: 0, org_id: "pym" },
  ];
  return {
    api: {
      listCustomers: vi.fn(async () => customers),
      listMessages: vi.fn(async () => [
        { id: "m1", customer_id: "c1", chat_id: "ch1", chat_status: "open", seq: 7,
          role: "seller", kind: "chat", body: "hello", summary_id: null,
          summary_json: null, created_at: "2026-01-01T00:00:00Z" },
      ]),
      listModels: vi.fn(async () => [
        { key: "sonnet-4-6", display_name: "Sonnet", provider: "anthropic" },
      ]),
      postMessage: vi.fn(async () => ({ messages: [], summary: null })),
      getCustomer: vi.fn(async () => customers[0]),
      listOrgs: vi.fn(async () => [
        { id: "pym", name: "Pym Technologies", tagline: null, is_catchall: false,
          product_count: 0, customer_count: 1, unbuilt_count: 0 },
      ]),
    },
  };
});

import { api } from "@/api/client";
import { ChatPage } from "./ChatPage";

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  vi.clearAllMocks();
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/chat/:customerId" element={<ChatPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function type(text: string) {
  renderAt("/chat/c1");
  await waitFor(() => expect(api.listMessages).toHaveBeenCalledWith("c1"));
  fireEvent.change(screen.getByPlaceholderText("Message…"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /send/i }));
}

describe("ChatPage message posting", () => {
  it("posts an ordinary message with the selected model key", async () => {
    await type("just chatting");
    await waitFor(() =>
      expect(api.postMessage).toHaveBeenCalledWith("c1", "seller", "just chatting", "sonnet-4-6"),
    );
  });

  it("posts a tagged message the same way — the server decides", async () => {
    await type("@agent create sales order");
    await waitFor(() =>
      expect(api.postMessage).toHaveBeenCalledWith(
        "c1", "seller", "@agent create sales order", "sonnet-4-6"),
    );
    expect(api.postMessage).toHaveBeenCalledTimes(1);
  });
});

describe("ChatPage deep links", () => {
  it("loads the customer from the URL", async () => {
    renderAt("/chat/c1");
    await waitFor(() => expect(api.listMessages).toHaveBeenCalledWith("c1"));
  });

  it("scrolls to the message named by ?seq=", async () => {
    renderAt("/chat/c1?seq=7");
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
  });
});
