import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Org } from "@/api/client";
import { api } from "@/api/client";
import { OrgsPage } from "./OrgsPage";

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      listOrgs: vi.fn(),
      createOrg: vi.fn(),
      updateOrg: vi.fn(),
      deleteOrg: vi.fn(),
      buildOrg: vi.fn(),
    },
  };
});

function org(over: Partial<Org>): Org {
  return {
    id: "pym", name: "Pym Technologies", tagline: "Amino acids", is_catchall: false,
    product_count: 5, customer_count: 2, unbuilt_count: 1, ...over,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <OrgsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.listOrgs).mockResolvedValue([
    org({}),
    org({ id: "damage-control", name: "Damage Control", is_catchall: true,
          product_count: 0, customer_count: 0, unbuilt_count: 0 }),
  ]);
});

describe("OrgsPage", () => {
  it("lists organizations with their counts", async () => {
    renderPage();
    expect(await screen.findByText("Pym Technologies")).toBeTruthy();
    expect(screen.getByText(/5 products/)).toBeTruthy();
    expect(screen.getByText(/2 customers/)).toBeTruthy();
  });

  it("links each organization to its scoped product list", async () => {
    renderPage();
    const link = await screen.findByRole("link", { name: /view catalog/i });
    expect(link.getAttribute("href")).toBe("/orgs/pym/products");
  });

  it("creates an organization", async () => {
    const user = userEvent.setup();
    vi.mocked(api.createOrg).mockResolvedValue(org({ id: "stark", name: "Stark Industries" }));
    renderPage();
    await screen.findByText("Pym Technologies");
    await user.click(screen.getByRole("button", { name: /add organization/i }));
    await user.type(screen.getByLabelText(/name/i), "Stark Industries");
    await user.click(screen.getByRole("button", { name: /^add$/i }));
    await waitFor(() =>
      expect(api.createOrg).toHaveBeenCalledWith("Stark Industries", ""));
  });

  it("does not offer delete on the catch-all organization", async () => {
    renderPage();
    await screen.findByText("Damage Control");
    const card = screen.getByText("Damage Control").closest("[data-org-card]")!;
    expect(card.querySelector("[data-delete]")).toBeNull();
  });

  it("surfaces the 409 reason when a delete is blocked", async () => {
    const user = userEvent.setup();
    vi.mocked(api.deleteOrg).mockRejectedValue(
      new Error("organization still has products or customers attached"));
    renderPage();
    await screen.findByText("Pym Technologies");
    await user.click(screen.getByRole("button", { name: /delete/i }));
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(await screen.findByText(/still has products or customers/i)).toBeTruthy();
  });

  it("builds embeddings for an organization", async () => {
    const user = userEvent.setup();
    vi.mocked(api.buildOrg).mockResolvedValue(org({ unbuilt_count: 0 }));
    renderPage();
    await screen.findByText("Pym Technologies");
    await user.click(screen.getByRole("button", { name: /build/i }));
    await waitFor(() => expect(api.buildOrg).toHaveBeenCalledWith("pym"));
  });
});
