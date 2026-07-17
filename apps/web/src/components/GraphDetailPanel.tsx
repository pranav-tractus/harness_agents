import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import type { GraphEdge, GraphNode } from "@/api/client";

export type SelectedElement =
  | { kind: "node"; element: GraphNode }
  | { kind: "edge"; element: GraphEdge }
  | null;

type Props = {
  selected: SelectedElement;
  onClose: () => void;
};

export function GraphDetailPanel({ selected, onClose }: Props) {
  const element = selected?.element ?? null;
  const properties = element
    ? Object.entries(element.properties).filter(([, v]) => v !== null && v !== "")
    : [];

  return (
    <Sheet open={selected !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <SheetContent>
        <SheetHeader className="mb-4">
          <div className="flex items-center gap-2">
            <Badge variant="outline">{element?.type ?? ""}</Badge>
            <SheetTitle className="text-base font-medium">{element?.label ?? ""}</SheetTitle>
          </div>
        </SheetHeader>
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
