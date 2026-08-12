import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type MetaRow = { id: string; key: string; value: string };

export function rowsToMeta(rows: MetaRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of rows) {
    const k = r.key.trim();
    if (k) out[k] = r.value;
  }
  return out;
}

export function metaToRows(meta: Record<string, string>): MetaRow[] {
  return Object.entries(meta ?? {}).map(([key, value]) => ({ id: `meta-${key}`, key, value }));
}

export function MetaEditor({
  rows,
  setRows,
}: {
  rows: MetaRow[];
  setRows: (r: MetaRow[]) => void;
}) {
  return (
    <div className="grid gap-2">
      {rows.map((r, i) => (
        <div key={r.id} className="flex gap-2">
          <Input
            placeholder="key (e.g. density)"
            value={r.key}
            onChange={(e) =>
              setRows(rows.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))
            }
          />
          <Input
            placeholder="value (e.g. 0.92 g/cm³)"
            value={r.value}
            onChange={(e) =>
              setRows(rows.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))
            }
          />
          <Button variant="outline" size="sm" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
            ✕
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        onClick={() => setRows([...rows, { id: `new-${Date.now()}`, key: "", value: "" }])}
      >
        Add metadata field
      </Button>
    </div>
  );
}
