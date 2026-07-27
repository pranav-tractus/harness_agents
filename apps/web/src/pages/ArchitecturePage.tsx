import { useState } from "react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ArchCanvas } from "@/components/arch/ArchCanvas";
import { ArchDetailPanel } from "@/components/arch/ArchDetailPanel";
import { KIND_COLORS, KIND_LABELS } from "@/components/arch/nodeTypes";
import { FLOWS, LAYERS, type ArchNode, type FlowId, type LayerId } from "@/architecture/types";

const KINDS = Object.keys(KIND_COLORS) as (keyof typeof KIND_COLORS)[];

export function ArchitecturePage() {
  const [layer, setLayer] = useState<LayerId>("context");
  const [activeFlow, setActiveFlow] = useState<FlowId | null>(null);
  const [selected, setSelected] = useState<ArchNode | null>(null);

  const current = LAYERS.find((l) => l.id === layer);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-3">
        <div className="flex items-center gap-4">
          <Tabs value={layer} onValueChange={(v) => v && setLayer(v as LayerId)}>
            <TabsList>
              {LAYERS.map((l) => (
                <TabsTrigger key={l.id} value={l.id} className="text-xs">
                  {l.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <p className="text-xs text-muted-foreground">{current?.blurb}</p>
        </div>

        {layer === "flows" ? (
          <div className="flex items-center gap-1.5">
            <span className="mr-1 text-xs text-muted-foreground">Highlight flow:</span>
            <Button
              size="sm"
              variant={activeFlow === null ? "default" : "outline"}
              className="h-7 text-xs"
              onClick={() => setActiveFlow(null)}
            >
              All
            </Button>
            {FLOWS.map((f) => (
              <Button
                key={f.id}
                size="sm"
                variant={activeFlow === f.id ? "default" : "outline"}
                className="h-7 text-xs"
                onClick={() => setActiveFlow(activeFlow === f.id ? null : f.id)}
              >
                <span
                  className="mr-1.5 inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: f.color }}
                />
                {f.label}
              </Button>
            ))}
          </div>
        ) : null}
      </div>

      <div className="relative flex-1">
        <ArchCanvas layer={layer} activeFlow={layer === "flows" ? activeFlow : null} onSelectNode={setSelected} />

        <div className="pointer-events-none absolute bottom-4 left-4 rounded-md border border-border bg-card/95 px-3 py-2 shadow-sm">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Legend
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {KINDS.map((k) => (
              <div key={k} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2 w-2 rounded-sm"
                  style={{ backgroundColor: KIND_COLORS[k] }}
                />
                <span className="text-[10px] text-muted-foreground">{KIND_LABELS[k]}</span>
              </div>
            ))}
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-px w-4 border-t border-dashed border-rose-400" />
              <span className="text-[10px] text-muted-foreground">early return</span>
            </div>
          </div>
        </div>
      </div>

      <ArchDetailPanel selected={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
