import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { GraphData, GraphNode } from "@/api/client";
import { GraphDetailPanel } from "./GraphDetailPanel";

const contract: GraphNode = {
  id: "Contract::k1",
  label: "rev1",
  type: "Contract",
  properties: { revision: 1, status: "draft" },
};

const graph: GraphData = {
  nodes: [
    contract,
    {
      id: "MessageRef::m1",
      label: "#3 customer",
      type: "MessageRef",
      properties: { seq: 3, role: "customer", snippet: "need 500 tons" },
    },
  ],
  edges: [
    { id: "e1", source: "Contract::k1", target: "MessageRef::m1", type: "DERIVED_FROM", properties: {} },
  ],
};

describe("GraphDetailPanel provenance", () => {
  it("lists derived message refs and fires navigation on click", () => {
    const onNavigate = vi.fn();
    render(
      <GraphDetailPanel
        selected={{ kind: "node", element: contract }}
        graph={graph}
        onClose={() => {}}
        onNavigateToMessage={onNavigate}
      />,
    );
    const ref = screen.getByText(/need 500 tons/);
    expect(ref).toBeInTheDocument();
    fireEvent.click(ref);
    expect(onNavigate).toHaveBeenCalledWith(3);
  });
});
