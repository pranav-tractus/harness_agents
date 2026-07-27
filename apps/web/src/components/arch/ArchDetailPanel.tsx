import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import type { ArchNode } from "@/architecture/types";
import { KIND_COLORS, KIND_LABELS } from "./nodeTypes";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </div>
      {children}
    </div>
  );
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="space-y-0.5">
      {items.map((item) => (
        <li key={item} className="font-mono text-[11px] text-foreground">
          {item}
        </li>
      ))}
    </ul>
  );
}

type Props = {
  selected: ArchNode | null;
  onClose: () => void;
};

export function ArchDetailPanel({ selected, onClose }: Props) {
  return (
    <Sheet open={selected !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-[420px] overflow-y-auto sm:max-w-[420px]">
        {selected ? (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: KIND_COLORS[selected.kind] }}
                />
                {selected.label}
              </SheetTitle>
            </SheetHeader>

            <div className="mt-4">
              <div className="mb-4 flex flex-wrap gap-1.5">
                <Badge variant="secondary">{KIND_LABELS[selected.kind]}</Badge>
                {selected.group ? <Badge variant="outline">{selected.group}</Badge> : null}
                {(selected.flows ?? []).map((f) => (
                  <Badge key={f} variant="outline">
                    {f}
                  </Badge>
                ))}
              </div>

              <Section title="What it does">
                <p className="text-sm leading-relaxed text-foreground">{selected.summary}</p>
              </Section>

              {selected.anchor ? (
                <Section title="Source">
                  <code className="block break-all rounded bg-muted px-2 py-1 font-mono text-[11px]">
                    {selected.anchor}
                  </code>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Open the file and search for the symbol after <code>::</code>.
                  </p>
                </Section>
              ) : null}

              {selected.reads?.length ? (
                <Section title="Reads">
                  <List items={selected.reads} />
                </Section>
              ) : null}

              {selected.writes?.length ? (
                <Section title="Writes">
                  <List items={selected.writes} />
                </Section>
              ) : null}

              {selected.invariant ? (
                <Section title="Invariant">
                  <p className="rounded border-l-2 border-amber-400 bg-amber-50 px-2.5 py-2 text-xs leading-relaxed text-amber-900">
                    {selected.invariant}
                  </p>
                </Section>
              ) : null}
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
