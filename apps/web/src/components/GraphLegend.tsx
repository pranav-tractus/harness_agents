import { NODE_COLORS } from "@/components/graph/nodes/parts";

const CUSTOMER_TYPES = ["Customer", "Chat", "Contract", "LineItem", "Term", "MessageRef", "Product", "Port"];
const PRODUCT_TYPES = ["Product", "Category", "Application", "Alias", "SpecAttr"];

const STATUS_GLYPHS: { glyph: string; label: string }[] = [
  { glyph: "✅", label: "agreed by both" },
  { glyph: "◑", label: "agreed by one" },
  { glyph: "○", label: "not agreed" },
  { glyph: "✔", label: "finalized" },
  { glyph: "✎", label: "draft" },
];

export function GraphLegend({ view }: { view: "customer" | "products" }) {
  const types = view === "products" ? PRODUCT_TYPES : CUSTOMER_TYPES;
  return (
    <div className="pointer-events-none absolute bottom-3 left-3 z-10 max-w-[220px] rounded-md border bg-card/90 p-2.5 text-[11px] shadow-sm backdrop-blur">
      <div className="mb-1.5 font-semibold">Legend</div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {types.map((t) => (
          <span key={t} className="flex items-center gap-1">
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ background: NODE_COLORS[t] ?? "#94a3b8" }}
            />
            {t}
          </span>
        ))}
      </div>
      {view === "customer" && (
        <div className="mt-2 flex flex-col gap-0.5 text-muted-foreground">
          {STATUS_GLYPHS.map((s) => (
            <span key={s.label}>
              <span className="mr-1">{s.glyph}</span>
              {s.label}
            </span>
          ))}
          <span>
            <span className="mr-1 inline-block border border-dashed border-amber-400 px-1 text-amber-600">
              dashed
            </span>
            inferred / unconfirmed
          </span>
        </div>
      )}
      {view === "products" && (
        <div className="mt-2 text-muted-foreground">badges: not built · built · stale</div>
      )}
    </div>
  );
}
