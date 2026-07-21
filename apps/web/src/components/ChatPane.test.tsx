import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Message } from "@/api/client";
import { ChatPane } from "./ChatPane";

function msg(seq: number, role: string, body: string, extra: Partial<Message> = {}): Message {
  return {
    id: `m${seq}`,
    customer_id: "c1",
    chat_id: "chat-1",
    chat_status: "active",
    seq,
    role,
    kind: "message",
    body,
    summary_id: null,
    summary_json: null,
    created_at: "2026-07-20T00:00:00Z",
    ...extra,
  };
}

// jsdom does not implement scrollIntoView; ChatPane calls it in its effects.
beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

describe("ChatPane provenance target", () => {
  it("tags each message row with its seq", () => {
    const { container } = render(
      <ChatPane messages={[msg(1, "seller", "hello"), msg(2, "customer", "hi")]} />,
    );
    expect(container.querySelector('[data-seq="1"]')).toBeTruthy();
    expect(container.querySelector('[data-seq="2"]')).toBeTruthy();
  });

  it("scrolls when a target seq is requested", () => {
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;
    render(<ChatPane messages={[msg(1, "seller", "hello"), msg(2, "customer", "hi")]} scrollToSeq={2} />);
    // called for the sticky-bottom effect and again for the seq-2 target lookup
    expect(scrollSpy).toHaveBeenCalled();
  });
});

describe("ChatPane agent rendering", () => {
  it("renders final card body as markdown (bold, not literal asterisks)", () => {
    const { container } = render(
      <ChatPane messages={[msg(1, "agent", "Done.\n\n- **tea** — qty 18 MT", { kind: "final" })]} />,
    );
    expect(container.querySelector("strong")?.textContent).toBe("tea");
    expect(container.textContent).not.toContain("**tea**");
  });

  it("shows a collapsible JSON block on a plain agent question", () => {
    render(
      <ChatPane messages={[msg(1, "agent", "Which product?",
        { kind: "question", summary_json: '{"mode":"clarify"}' })]} />,
    );
    expect(screen.getByText(/Raw model response \(JSON\)/i)).toBeTruthy();
    expect(screen.getByText(/"mode":"clarify"/)).toBeTruthy();
  });

  it("highlights the @agent mention in a seller message", () => {
    const { container } = render(
      <ChatPane messages={[msg(1, "seller", "@agent create sales order")]} />,
    );
    const chip = container.querySelector('[data-testid="agent-mention"]');
    expect(chip?.textContent).toBe("@agent");
    expect(container.textContent).toContain("create sales order");
  });

  it("renders a checkpoint divider after a finished chat's last message", () => {
    const { getByText } = render(
      <ChatPane
        messages={[
          msg(1, "agent", "Approved.", { kind: "final", chat_id: "chat-1", chat_status: "finished" }),
          msg(1, "seller", "next deal", { id: "m2", chat_id: "chat-2", chat_status: "active" }),
        ]}
      />,
    );
    expect(getByText(/Contract finalized · new chat started/)).toBeTruthy();
    // active chat's messages do not get a trailing divider
    const dividers = document.querySelectorAll('[data-testid="chat-checkpoint"]');
    expect(dividers.length).toBe(1);
  });
});
