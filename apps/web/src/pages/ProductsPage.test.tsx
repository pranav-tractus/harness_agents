import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Product } from "@/api/client";
import { api } from "@/api/client";
import { ProductsPage } from "./ProductsPage";

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, api: { ...actual.api, listProducts: vi.fn() } };
});

function product(over: Partial<Product>): Product {
  return {
    id: "p1", code: "P-1", name: "Product One", short_description: "d",
    long_description: null, spec: null, metadata: {}, build_status: "built",
    source_label: null, ...over,
  };
}

describe("ProductsPage source filter", () => {
  beforeEach(() => {
    vi.mocked(api.listProducts).mockResolvedValue([
      product({ id: "og", code: "OG-1", source_label: "OG Files" }),
      product({ id: "test", code: "TEST-1", source_label: "Test Files" }),
    ]);
  });

  it("shows all products by default", async () => {
    render(<ProductsPage />);
    expect(await screen.findByText("OG-1")).toBeTruthy();
    expect(screen.getByText("TEST-1")).toBeTruthy();
  });

  it("filters to only Test Files products when selected", async () => {
    const user = userEvent.setup();
    render(<ProductsPage />);
    await screen.findByText("OG-1");

    const trigger = screen.getByRole("combobox", { name: /source/i });
    await user.click(trigger);
    const listbox = await screen.findByRole("listbox");
    await user.click(within(listbox).getByText("Test Files"));

    expect(screen.queryByText("OG-1")).toBeNull();
    expect(screen.getByText("TEST-1")).toBeTruthy();
  });
});
