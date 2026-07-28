import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { GraphNode } from "@/api/client";

export const NODE_COLORS: Record<string, string> = {
  Customer: "#6366f1",
  Chat: "#0ea5e9",
  Contract: "#8b5cf6",
  LineItem: "#10b981",
  Term: "#f59e0b",
  Product: "#059669",
  Port: "#f97316",
  MessageRef: "#64748b",
  Attribute: "#a855f7",
  Preference: "#d946ef",
  Category: "#ef4444",
  Application: "#0891b2",
  Alias: "#0ea5e9",

};

export function agreementLevel(agreedBy: unknown): "both" | "one" | "none" {
  const arr = Array.isArray(agreedBy) ? (agreedBy as string[]) : [];
  const seller = arr.includes("seller");
  const customer = arr.includes("customer");
  if (seller && customer) return "both";
  if (seller || customer) return "one";
  return "none";
}

export function AgreementGlyph({ agreedBy }: { agreedBy: unknown }) {
  const level = agreementLevel(agreedBy);
  const glyph = level === "both" ? "✅" : level === "one" ? "◑" : "○";
  const title =
    level === "both"
      ? "Agreed by seller and customer"
      : level === "one"
        ? "Agreed by one party"
        : "Not agreed";
  return (
    <span title={title} aria-label={title} className="text-xs leading-none">
      {glyph}
    </span>
  );
}

export function isInferred(node: GraphNode): boolean {
  const p = node.properties;
  return p.inferred === true || p.source === "inferred" || p.confidence === "low";
}

export function InferredTag() {
  return (
    <Badge
      variant="outline"
      className="border-dashed border-amber-400 text-amber-600 text-[10px]"
    >
      inferred
    </Badge>
  );
}

export function BuildBadge({ status }: { status: string }) {
  const cls =
    status === "built"
      ? "text-emerald-600 border-emerald-300"
      : status === "stale"
        ? "text-amber-600 border-amber-300"
        : "text-muted-foreground";
  return (
    <Badge variant="outline" className={cn("text-[10px]", cls)}>
      {status}
    </Badge>
  );
}

export function ChatStatusChip({ status }: { status?: string }) {
  const s = status || "active";
  return (
    <Badge variant="outline" className="text-[10px]">
      {s}
    </Badge>
  );
}

export function contractGlyph(status?: string): string {
  return status === "finalized" ? "✔ finalized" : "✎ draft";
}

export function ExpandCaret({
  expanded,
  onToggle,
}: {
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={expanded ? "Collapse" : "Expand"}
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      className="ml-1 text-xs leading-none text-muted-foreground hover:text-foreground"
    >
      {expanded ? "▾" : "▸"}
    </button>
  );
}

export function NodeShell({
  color,
  dashed,
  children,
}: {
  color?: string;
  dashed?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "min-w-[120px] rounded-md border bg-card px-2.5 py-1.5 text-xs shadow-sm",
        dashed && "border-dashed border-amber-400 bg-amber-50",
      )}
      style={{ borderLeft: color ? `4px solid ${color}` : undefined }}
    >
      {children}
    </div>
  );
}
