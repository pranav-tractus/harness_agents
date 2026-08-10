import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Customer, Org } from "@/api/client";
import { CustomerSidebar } from "./CustomerSidebar";

function customer(over: Partial<Customer>): Customer {
  return {
    id: "c1", name: "Acme", profile: {} as Customer["profile"],
    last_contract_seq: 0, org_id: "pym", ...over,
  };
}

const ORGS: Org[] = [
  { id: "pym", name: "Pym Technologies", tagline: null, is_catchall: false,
    product_count: 0, customer_count: 1, unbuilt_count: 0 },
  { id: "roxxon", name: "Roxxon Energy Corporation", tagline: null, is_catchall: false,
    product_count: 0, customer_count: 1, unbuilt_count: 0 },
];

function renderSidebar(over: Partial<Parameters<typeof CustomerSidebar>[0]> = {}) {
  const props = {
    customers: [customer({}), customer({ id: "c2", name: "Beta", org_id: "roxxon" })],
    orgs: ORGS,
    selectedId: "c1",
    onSelect: vi.fn(),
    onAdd: vi.fn(async () => {}),
    onDelete: vi.fn(async () => {}),
    ...over,
  };
  render(<CustomerSidebar {...props} />);
  return props;
}

describe("CustomerSidebar", () => {
  it("groups customers under their organization", () => {
    renderSidebar();
    const pymGroup = screen.getByRole("group", { name: "Pym Technologies" });
    expect(within(pymGroup).getByText("Acme")).toBeTruthy();
    expect(within(pymGroup).queryByText("Beta")).toBeNull();
  });

  it("requires an organization when adding a customer", async () => {
    const user = userEvent.setup();
    const props = renderSidebar();
    await user.click(screen.getByRole("button", { name: "Add" }));
    await user.type(screen.getByLabelText(/name/i), "Gamma");

    const submit = screen.getByRole("button", { name: /^add$/i });
    expect(submit.hasAttribute("disabled")).toBe(true);

    await user.click(screen.getByRole("combobox", { name: /organization/i }));
    await user.click(within(await screen.findByRole("listbox")).getByText("Roxxon Energy Corporation"));
    await user.click(screen.getByRole("button", { name: /^add$/i }));

    expect(props.onAdd).toHaveBeenCalledWith("Gamma", "roxxon");
  });
});
