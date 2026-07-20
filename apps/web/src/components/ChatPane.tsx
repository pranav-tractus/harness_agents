import { useEffect, useRef } from "react";
import { type Message } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Markdown } from "@/components/Markdown";
import { cn } from "@/lib/utils";

const NEAR_BOTTOM_PX = 80;

type Props = {
  messages: Message[];
  scrollToSeq?: number | null;
};

function roleLabel(role: string) {
  if (role === "me" || role === "seller") return "Seller";
  if (role === "customer") return "Customer";
  if (role === "agent" || role === "assistant") return "Agent";
  return role;
}

function isSellerRole(role: string) {
  return role === "me" || role === "seller";
}

function isAgentRole(role: string) {
  return role === "agent" || role === "assistant";
}

export function ChatPane({ messages, scrollToSeq }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current =
      el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX;
  }

  useEffect(() => {
    if (stickToBottom.current) {
      bottomRef.current?.scrollIntoView({ behavior: "instant" });
    }
  }, [messages]);

  // Depends on scrollToSeq only (not messages): ChatPage sets scrollToSeq after
  // the target message is already loaded, so re-scrolling on later message
  // updates (e.g. a new chat message) would be wrong.
  useEffect(() => {
    if (scrollToSeq == null) return;
    const el = scrollRef.current?.querySelector<HTMLElement>(`[data-seq="${scrollToSeq}"]`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("ring-2", "ring-primary");
    const timer = setTimeout(() => el.classList.remove("ring-2", "ring-primary"), 1600);
    return () => clearTimeout(timer);
  }, [scrollToSeq]);

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="flex-1 space-y-2.5 overflow-y-auto p-4"
    >
      {messages.length === 0 && (
        <p className="text-sm text-muted-foreground">No messages yet. Start the conversation.</p>
      )}
      {messages.map((message) => {
        if (["summary", "draft", "final"].includes(message.kind)) {
          const label = message.kind === "final" ? "Finalized contract"
            : message.kind === "draft" ? "Draft contract" : "AI Summary";
          return (
            <Card key={message.id} data-seq={message.seq} className="border-primary/20 bg-primary/5">
              <CardContent className="space-y-2 p-4">
                <Badge variant="secondary">{label}</Badge>
                <pre className="whitespace-pre-wrap text-sm">{message.body}</pre>
                {message.summary_json && (
                  <details className="text-xs">
                    <summary className="cursor-pointer select-none text-muted-foreground hover:text-foreground">
                      Raw model response (JSON)
                    </summary>
                    <pre className="mt-2 max-h-80 overflow-auto rounded-md bg-muted p-3 font-mono text-[11px] leading-relaxed">
                      {message.summary_json}
                    </pre>
                  </details>
                )}
              </CardContent>
            </Card>
          );
        }

        if (message.kind === "question") {
          return (
            <div
              key={message.id}
              data-seq={message.seq}
              className="mx-auto w-full max-w-full rounded-lg border-l-2 border-primary/40 bg-primary/5 px-4 py-2.5 text-sm"
            >
              <div className="mb-1 flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {roleLabel(message.role)}
                </span>
                <Badge variant="outline" className="text-[10px]">needs answer</Badge>
              </div>
              <Markdown className="leading-relaxed">{message.body}</Markdown>
            </div>
          );
        }

        return (
          <div
            key={message.id}
            data-seq={message.seq}
            className={cn(
              "max-w-[40%] rounded-md px-3.5 py-2.5 text-sm",
              isSellerRole(message.role) &&
                "ml-auto bg-primary text-primary-foreground shadow-sm",
              message.role === "customer" &&
                "mr-auto border bg-card shadow-sm",
              isAgentRole(message.role) &&
                "mx-auto w-full max-w-full rounded-lg border-l-2 border-primary/40 bg-primary/5 px-4",
              message.kind === "command" && "opacity-70",
            )}
          >
            <div
              className={cn(
                "mb-1 text-[10px] font-semibold uppercase tracking-wide",
                isSellerRole(message.role) ? "opacity-70" : "text-muted-foreground",
              )}
            >
              {roleLabel(message.role)}
              {message.kind === "command" ? " · command" : ""}
            </div>
            {isAgentRole(message.role) ? (
              <Markdown className="leading-relaxed">{message.body}</Markdown>
            ) : (
              <div className="whitespace-pre-wrap leading-relaxed">{message.body}</div>
            )}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
