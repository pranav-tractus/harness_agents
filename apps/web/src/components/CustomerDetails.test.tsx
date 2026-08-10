import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Customer, Org } from "@/api/client";
import { api } from "@/api/client";
import { CustomerDetails } from "./CustomerDetails";

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, api: { ...actual.api, updateProfile: vi.fn() } };
});

const ORGS: Org[] = [
  { id: "pym", name: "Pym Technologies", tagline: null, is_catchall: false,
    product_count: 0, customer_count: 1, unbuilt_count: 0 },
  { id: "roxxon", name: "Roxxon Energy Corporation", tagline: null, is_catchall: false,
    product_count: 0, customer_count: 0, unbuilt_count: 0 },
];

const CUSTOMER: Customer = {
  id: "c1", name: "Acme", last_contract_seq: 0, org_id: "pym",
  profile: {
    email: null, phone: null, business_address: null, delivery_address: null,
    contact_point: null, approved_credit_term: null, approved_white_label: null,
    latest_packing_and_loading: null,
  },
};

beforeEach(() => vi.clearAllMocks());

describe("CustomerDetails", () => {
  it("shows the organization name", () => {
    render(<CustomerDetails customer={CUSTOMER} orgs={ORGS} onUpdated={vi.fn()} />);
    expect(screen.getByText("Pym Technologies")).toBeTruthy();
  });

  it("moves the customer to another organization", async () => {
    const user = userEvent.setup();
    vi.mocked(api.updateProfile).mockResolvedValue({ ...CUSTOMER, org_id: "roxxon" });
    render(<CustomerDetails customer={CUSTOMER} orgs={ORGS} onUpdated={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /edit/i }));
    await user.click(screen.getByRole("combobox", { name: /organization/i }));
    await user.click(within(await screen.findByRole("listbox")).getByText("Roxxon Energy Corporation"));
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(api.updateProfile).toHaveBeenCalledWith("c1", expect.anything(), "roxxon"));
  });
});
