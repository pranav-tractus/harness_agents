import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GraphNode } from "@/api/client";
import { LineItemContent } from "./LineItemNode";
import { TermContent } from "./TermNode";

const line: GraphNode = {
  id: "LineItem::l1",
  label: "PX-100",
  type: "LineItem",
  properties: {
    product_code: "PX-100",
    quantity: 500,
    unit: "tons",
    price: 1200,
    price_unit: "USD",
    incoterm: "FOB",
    agreed_by: ["seller"],
  },
};

const inferredTerm: GraphNode = {
  id: "Term::t1",
  label: "payment: NET30",
  type: "Term",
  properties: { kind: "payment", value: "NET30", agreed_by: [], inferred: true },
};

describe("LineItemContent", () => {
  it("renders code, quantity and price inline", () => {
    render(
      <LineItemContent node={line} expanded={false} hasChildren={false} onToggle={() => {}} />,
    );
    expect(screen.getByText(/PX-100/)).toBeInTheDocument();
    expect(screen.getByText(/500/)).toBeInTheDocument();
    expect(screen.getByText(/1200/)).toBeInTheDocument();
  });
});

describe("TermContent", () => {
  it("marks an inferred term", () => {
    render(<TermContent node={inferredTerm} />);
    expect(screen.getByText("inferred")).toBeInTheDocument();
  });
});
