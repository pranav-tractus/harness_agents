import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GraphNode } from "@/api/client";
import { LeafContent } from "./LeafNode";

const product: GraphNode = {
  id: "Product::PX-100",
  label: "PX-100",
  type: "Product",
  properties: { code: "PX-100", description: "Polymer X", build_status: "stale" },
};

const messageRef: GraphNode = {
  id: "MessageRef::m1",
  label: "#3 customer",
  type: "MessageRef",
  properties: { seq: 3, role: "customer", snippet: "we need 500 tons" },
};

describe("LeafContent", () => {
  it("renders a stale product build badge", () => {
    render(<LeafContent node={product} />);
    expect(screen.getByText("PX-100")).toBeInTheDocument();
    expect(screen.getByText("stale")).toBeInTheDocument();
  });

  it("renders a built product build badge", () => {
    render(<LeafContent node={{ ...product, properties: { ...product.properties, build_status: "built" } }} />);
    expect(screen.getByText("built")).toBeInTheDocument();
  });

  it("renders a message ref with seq, role and snippet", () => {
    render(<LeafContent node={messageRef} />);
    expect(screen.getByText(/#3/)).toBeInTheDocument();
    expect(screen.getByText(/we need 500 tons/)).toBeInTheDocument();
  });
});
