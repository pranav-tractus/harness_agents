import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MessageComposer } from "./MessageComposer";

describe("MessageComposer", () => {
  it("submits trimmed text via onMessage and exposes roles", () => {
    const onMessage = vi.fn();
    render(<MessageComposer role="seller" onRoleChange={() => {}} onMessage={onMessage} />);
    fireEvent.change(screen.getByPlaceholderText("Message…"), { target: { value: "  hi  " } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(onMessage).toHaveBeenCalledWith("hi");
    expect(screen.getByText("Seller")).toBeTruthy();
  });

  it("no longer renders Ask agent or Approve buttons", () => {
    render(<MessageComposer role="seller" onRoleChange={() => {}} onMessage={() => {}} />);
    expect(screen.queryByRole("button", { name: /ask agent/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
  });
});
