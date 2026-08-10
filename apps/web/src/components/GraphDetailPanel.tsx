import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import type { GraphData, GraphEdge, GraphNode } from "@/api/client";
import { provenanceFor, supersedesChain } from "@/components/graph/hierarchy";
import { agreementLevel } from "@/components/graph/nodes/parts";

export type SelectedElement =
  | { kind: "node"; element: GraphNode }
  | { kind: "edge"; element: GraphEdge }
  | null;

type Props = {
  selected: SelectedElement;
  graph: GraphData;
  onClose: () => void;
  onNavigateToMessage?: (seq: number) => void;
};

function AgreementRow({ agreedBy }: { agreedBy: unknown }) {
  const arr = Array.isArray(agreedBy) ? (agreedBy as string[]) : [];
  const level = agreementLevel(agreedBy);
  return (
    <div className="mb-4">
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Agreement
      </div>
      <div className="flex items-center gap-2 text-sm">
        <Badge variant={arr.includes("seller") ? "default" : "outline"}>seller</Badge>
        <Badge variant={arr.includes("customer") ? "default" : "outline"}>customer</Badge>
        <span className="text-muted-foreground">
          {level === "both" ? "fully agreed" : level === "one" ? "partially agreed" : "not agreed"}
        </span>
      </div>
    </div>
  );
}

export function GraphDetailPanel({
  selected,
  graph,
  onClose,
  onNavigateToMessage,
}: Props) {
  const node = selected?.kind === "node" ? selected.element : null;
  const element = selected?.element ?? null;
  const displayTitle =
    selected?.kind === "node"
      ? selected.element.label
      : selected?.kind === "edge"
        ? selected.element.type
        : "";
  const properties = element
    ? Object.entries(element.properties).filter(([, v]) => v !== null && v !== "")
    : [];

  const provenance = node ? provenanceFor(node, graph) : [];
  const lineage = node?.type === "Contract" ? supersedesChain(node.id, graph) : [];
  const showAgreement = node ? Array.isArray(node.properties.agreed_by) : false;

  return (
    <Sheet open={selected !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <SheetContent>
        <SheetHeader className="mb-4">
          <div className="flex items-center gap-2">
            <Badge variant="outline">{element?.type ?? ""}</Badge>
            <SheetTitle className="text-base font-medium">{displayTitle}</SheetTitle>
          </div>
        </SheetHeader>

        {showAgreement && <AgreementRow agreedBy={node?.properties.agreed_by} />}

        {lineage.length > 0 && (
          <div className="mb-4">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Revision lineage
            </div>
            <ul className="space-y-1 text-sm">
              {lineage.map((c) => (
                <li key={c.id} className="text-muted-foreground">
                  ← rev {String(c.properties.revision ?? "?")} ({String(c.properties.status ?? "")})
                </li>
              ))}
            </ul>
          </div>
        )}

        {provenance.length > 0 && (
          <div className="mb-4">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Provenance
            </div>
            <ul className="space-y-1">
              {provenance.map((m) => (
                <li key={m.id}>
                  <button
                    type="button"
                    onClick={() => onNavigateToMessage?.(Number(m.properties.seq))}
                    className="w-full rounded-md border px-2 py-1.5 text-left text-xs hover:bg-muted"
                  >
                    <span className="font-medium">
                      #{String(m.properties.seq)} {String(m.properties.role)}
                    </span>
                    <span className="ml-1 text-muted-foreground">
                      {String(m.properties.snippet ?? "")}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {properties.length === 0 ? (
          <p className="text-sm text-muted-foreground">No properties.</p>
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {properties.map(([key, value]) => (
                <tr key={key} className="border-b last:border-0">
                  <td className="py-1.5 pr-4 font-medium text-muted-foreground whitespace-nowrap">{key}</td>
                  <td className="py-1.5 break-all">{String(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </SheetContent>
    </Sheet>
  );
}
