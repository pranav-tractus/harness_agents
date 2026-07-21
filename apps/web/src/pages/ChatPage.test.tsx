import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/client", () => {
  const customers = [{ id: "c1", name: "Acme", profile: {}, last_contract_seq: 0 }];
  return {
    api: {
      listCustomers: vi.fn(async () => customers),
      listMessages: vi.fn(async () => []),
      listModels: vi.fn(async () => [{ key: "sonnet-4-6", display_name: "Sonnet", provider: "anthropic" }]),
      postMessage: vi.fn(async () => ({})),
      invokeAgent: vi.fn(async () => ({ messages: [], summary: null })),
      getCustomer: vi.fn(async () => customers[0]),
    },
  };
});

import { api } from "@/api/client";
import { ChatPage } from "./ChatPage";

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  vi.clearAllMocks();
});

async function type(text: string) {
  render(<ChatPage />);
  await waitFor(() => expect(api.listCustomers).toHaveBeenCalled());
  fireEvent.change(screen.getByPlaceholderText("Message…"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /send/i }));
}

describe("ChatPage @agent routing", () => {
  it("posts a normal message without invoking the agent", async () => {
    await type("just chatting");
    await waitFor(() => expect(api.postMessage).toHaveBeenCalledWith("c1", "seller", "just chatting"));
    expect(api.invokeAgent).not.toHaveBeenCalled();
  });

  it("posts then asks the agent when tagged", async () => {
    await type("@agent create sales order");
    await waitFor(() => expect(api.invokeAgent).toHaveBeenCalledWith("c1", "sonnet-4-6", "ask"));
    expect(api.postMessage).toHaveBeenCalledWith("c1", "seller", "@agent create sales order");
  });

  it("routes @agent confirm to approve", async () => {
    await type("@agent confirm");
    await waitFor(() => expect(api.invokeAgent).toHaveBeenCalledWith("c1", "sonnet-4-6", "approve"));
  });
});
