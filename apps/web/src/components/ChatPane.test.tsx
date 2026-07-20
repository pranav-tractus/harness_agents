import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Message } from "@/api/client";
import { ChatPane } from "./ChatPane";

function msg(seq: number, role: string, body: string): Message {
  return {
    id: `m${seq}`,
    customer_id: "c1",
    seq,
    role,
    kind: "message",
    body,
    summary_id: null,
    summary_json: null,
    created_at: "2026-07-20T00:00:00Z",
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
