import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("@/pages/ChatPage", () => ({ ChatPage: () => <div>chat page</div> }));
vi.mock("@/pages/ProductsPage", () => ({ ProductsPage: () => <div>products page</div> }));
vi.mock("@/pages/GraphsPage", () => ({ GraphsPage: () => <div>graphs page</div> }));
vi.mock("@/pages/OrgsPage", () => ({ OrgsPage: () => <div>orgs page</div> }));
vi.mock("@/pages/ArchitecturePage", () => ({ ArchitecturePage: () => <div>architecture page</div> }));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App routing", () => {
  it("renders the chat page at /chat/:customerId", () => {
    renderAt("/chat/c1");
    expect(screen.getByText("chat page")).toBeTruthy();
  });

  it("renders the orgs page at /orgs", () => {
    renderAt("/orgs");
    expect(screen.getByText("orgs page")).toBeTruthy();
  });

  it("renders the products page at /orgs/:orgId/products", () => {
    renderAt("/orgs/pym/products");
    expect(screen.getByText("products page")).toBeTruthy();
  });

  it("renders the products page at /products", () => {
    renderAt("/products");
    expect(screen.getByText("products page")).toBeTruthy();
  });

  it("renders the architecture page at /architecture", () => {
    renderAt("/architecture");
    expect(screen.getByText("architecture page")).toBeTruthy();
  });

  it("renders a not-found page for an unknown route", () => {
    renderAt("/nowhere");
    expect(screen.getByText(/page not found/i)).toBeTruthy();
  });

  it("marks the active nav link", () => {
    renderAt("/orgs");
    expect(screen.getByRole("link", { name: "Organizations" }).getAttribute("aria-current"))
      .toBe("page");
  });

  it("keeps the Chat nav link active on a customer route", () => {
    renderAt("/chat/c1");
    expect(screen.getByRole("link", { name: "Chat" }).getAttribute("aria-current"))
      .toBe("page");
  });
});
