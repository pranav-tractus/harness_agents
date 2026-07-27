import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GraphLegend } from "./GraphLegend";

describe("GraphLegend", () => {
  it("lists customer-view node types and status glyphs", () => {
    render(<GraphLegend view="customer" />);
    expect(screen.getByText("Chat")).toBeInTheDocument();
    expect(screen.getByText("Contract")).toBeInTheDocument();
    expect(screen.getByText("LineItem")).toBeInTheDocument();
    expect(screen.getByText(/agreed by both/i)).toBeInTheDocument();
  });

  it("lists product-view node types", () => {
    render(<GraphLegend view="products" />);
    expect(screen.getByText("Product")).toBeInTheDocument();
    expect(screen.getByText("Category")).toBeInTheDocument();
  });
});
