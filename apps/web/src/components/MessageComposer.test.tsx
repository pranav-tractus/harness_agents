import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MessageComposer } from "./MessageComposer";

describe("MessageComposer agent controls", () => {
  it("fires onAskAgent and exposes seller/customer roles", () => {
    const onAskAgent = vi.fn();
    render(
      <MessageComposer role="seller" onRoleChange={() => {}} onMessage={() => {}}
        onAskAgent={onAskAgent} onApprove={() => {}} showApprove={false} />,
    );
    expect(screen.getByRole("button", { name: /ask agent/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /ask agent/i }));
    expect(onAskAgent).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Seller")).toBeTruthy();
  });
});
