import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Org, Product } from "@/api/client";
import { api } from "@/api/client";
import { ProductsPage } from "./ProductsPage";

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      listProducts: vi.fn(),
      listOrgs: vi.fn(),
      updateProduct: vi.fn(),
    },
  };
});

function product(over: Partial<Product>): Product {
  return {
    id: "p1", code: "P-1", name: "Product One", short_description: "d",
    long_description: null, spec: null, metadata: {}, build_status: "built",
    source_label: null, org_id: "pym", ...over,
  };
}

function org(over: Partial<Org>): Org {
  return {
    id: "pym", name: "Pym Technologies", tagline: null, is_catchall: false,
    product_count: 1, customer_count: 0, unbuilt_count: 0, ...over,
  };
}

const ORGS = [org({}), org({ id: "roxxon", name: "Roxxon Energy Corporation" })];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.listOrgs).mockResolvedValue(ORGS);
  vi.mocked(api.listProducts).mockResolvedValue([
    product({ id: "og", code: "OG-1", source_label: "OG Files", org_id: "pym" }),
    product({ id: "test", code: "TEST-1", source_label: "Test Files", org_id: "roxxon" }),
  ]);
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/products" element={<ProductsPage />} />
        <Route path="/orgs/:orgId/products" element={<ProductsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProductsPage org scoping", () => {
  it("requests only the org's products on the scoped route", async () => {
    renderAt("/orgs/pym/products");
    await waitFor(() => expect(api.listProducts).toHaveBeenCalledWith("pym"));
  });

  it("requests every product on the global route", async () => {
    renderAt("/products");
    await waitFor(() => expect(api.listProducts).toHaveBeenCalledWith(undefined));
  });

  it("shows an Organization column only on the global route", async () => {
    renderAt("/products");
    expect(await screen.findByRole("columnheader", { name: /organization/i })).toBeTruthy();
    expect(screen.getByText("Roxxon Energy Corporation")).toBeTruthy();
  });

  it("hides the Organization column on the scoped route", async () => {
    vi.mocked(api.listProducts).mockResolvedValue([product({ id: "og", code: "OG-1" })]);
    renderAt("/orgs/pym/products");
    await screen.findByText("OG-1");
    expect(screen.queryByRole("columnheader", { name: /organization/i })).toBeNull();
  });

  it("names the org in the heading on the scoped route", async () => {
    renderAt("/orgs/pym/products");
    expect(await screen.findByRole("heading", { name: /pym technologies/i })).toBeTruthy();
  });
});

describe("ProductsPage source filter", () => {
  it("shows all products by default", async () => {
    renderAt("/products");
    expect(await screen.findByText("OG-1")).toBeTruthy();
    expect(screen.getByText("TEST-1")).toBeTruthy();
  });

  it("filters to only Test Files products when selected", async () => {
    const user = userEvent.setup();
    renderAt("/products");
    await screen.findByText("OG-1");

    const trigger = screen.getByRole("combobox", { name: /source/i });
    await user.click(trigger);
    const listbox = await screen.findByRole("listbox");
    await user.click(within(listbox).getByText("Test Files"));

    expect(screen.queryByText("OG-1")).toBeNull();
    expect(screen.getByText("TEST-1")).toBeTruthy();
  });
});

describe("ProductsPage org moves", () => {
  it("sends the new org when the edit dialog changes it", async () => {
    const user = userEvent.setup();
    vi.mocked(api.updateProduct).mockResolvedValue(product({ org_id: "roxxon" }));
    vi.mocked(api.listProducts).mockResolvedValue([product({ id: "og", code: "OG-1" })]);
    renderAt("/products");
    await screen.findByText("OG-1");

    await user.click(screen.getByRole("button", { name: /edit/i }));
    const orgSelect = screen.getByRole("combobox", { name: /organization/i });
    await user.click(orgSelect);
    const listbox = await screen.findByRole("listbox");
    await user.click(within(listbox).getByText("Roxxon Energy Corporation"));
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(api.updateProduct).toHaveBeenCalledWith(
        "og", expect.objectContaining({ org_id: "roxxon" })));
  });
});
