import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/client", () => ({
  api: {
    listCustomers: vi.fn(async () => [
      { id: "c1", name: "Acme", profile: {}, last_contract_seq: 0, org_id: "pym" },
      { id: "c2", name: "Beta", profile: {}, last_contract_seq: 0, org_id: "roxxon" },
    ]),
    getCustomerGraph: vi.fn(async () => ({ nodes: [], edges: [] })),
  },
}));

// @xyflow/react needs layout APIs jsdom does not provide, and the real detail
// panel only renders once a node is selected — stub both down to the one
// interaction this page owns.
vi.mock("@/components/GraphCanvas", () => ({ GraphCanvas: () => <div>canvas</div> }));
vi.mock("@/components/GraphLegend", () => ({ GraphLegend: () => null }));
vi.mock("@/components/GraphDetailPanel", () => ({
  GraphDetailPanel: ({ onNavigateToMessage }: { onNavigateToMessage: (s: number) => void }) => (
    <button data-testid="jump-to-message" onClick={() => onNavigateToMessage(7)}>
      jump
    </button>
  ),
}));

import { api } from "@/api/client";
import { GraphsPage } from "./GraphsPage";

function Probe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname + loc.search}</div>;
}

describe("GraphsPage", () => {
  it("loads the graph for the customer in the URL", async () => {
    render(
      <MemoryRouter initialEntries={["/graphs/c1"]}>
        <Routes>
          <Route path="/graphs/:customerId" element={<GraphsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(api.getCustomerGraph).toHaveBeenCalledWith("c1"));
  });

  it("navigates to the chat message URL when the detail panel asks", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/graphs/c1"]}>
        <Probe />
        <Routes>
          <Route path="/graphs/:customerId" element={<GraphsPage />} />
          <Route path="/chat/:customerId" element={<div>chat</div>} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(api.getCustomerGraph).toHaveBeenCalled());
    await user.click(screen.getByTestId("jump-to-message"));
    expect(screen.getByTestId("loc").textContent).toBe("/chat/c1?seq=7");
  });

  it("loads a different customer's graph when the picker changes", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/graphs/c1"]}>
        <Probe />
        <Routes>
          <Route path="/graphs/:customerId" element={<GraphsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(api.getCustomerGraph).toHaveBeenCalledWith("c1"));
    await user.click(screen.getByRole("combobox", { name: /customer/i }));
    await user.click(within(await screen.findByRole("listbox")).getByText("Beta"));
    expect(screen.getByTestId("loc").textContent).toBe("/graphs/c2");
  });
});
