// Generates docs/architecture.md from src/architecture/spec.ts.
// Run: npm run gen:arch
// Node v24 strips TypeScript types natively, so this needs no build step.
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { EDGES, NODES } from "../src/architecture/spec.ts";
import { LAYERS } from "../src/architecture/types.ts";
import type { ArchEdge, ArchNode } from "../src/architecture/types.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "../../../docs/architecture.md");

/** Mermaid node ids may not contain dots or dashes. */
function mid(id: string): string {
  return id.replace(/[^a-zA-Z0-9]/g, "_");
}

function esc(text: string): string {
  return text.replace(/"/g, "'");
}

function shape(node: ArchNode): string {
  const label = `"${esc(node.label)}"`;
  if (node.kind === "gate") return `{{${label}}}`;
  if (node.kind === "store") return `[(${label})]`;
  if (node.kind === "external") return `([${label}])`;
  return `[${label}]`;
}

function arrow(edge: ArchEdge): string {
  const label = edge.label ? `|"${esc(edge.label)}"|` : "";
  return edge.kind === "gate-fail" ? `-.->${label}` : `-->${label}`;
}

function mermaidFor(layer: string): string {
  const nodes = NODES.filter((n) => n.layer === layer);
  const edges = EDGES.filter((e) => e.layer === layer);
  const groups = new Map<string, ArchNode[]>();
  for (const n of nodes) {
    const key = n.group ?? "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(n);
  }

  const lines: string[] = ["```mermaid", "flowchart LR"];
  for (const [group, members] of groups) {
    const indent = group ? "    " : "  ";
    if (group) lines.push(`  subgraph ${mid(group)}["${esc(group)}"]`);
    for (const n of members) lines.push(`${indent}${mid(n.id)}${shape(n)}`);
    if (group) lines.push("  end");
  }
  for (const e of edges) {
    lines.push(`  ${mid(e.source)} ${arrow(e)} ${mid(e.target)}`);
  }
  const gateIds = nodes.filter((n) => n.kind === "gate").map((n) => mid(n.id));
  if (gateIds.length > 0) {
    lines.push(`  classDef gate stroke:#f43f5e,stroke-dasharray:5 4,fill:#fff1f2;`);
    lines.push(`  class ${gateIds.join(",")} gate;`);
  }
  lines.push("```");
  return lines.join("\n");
}

function detailsFor(layer: string): string {
  const nodes = NODES.filter((n) => n.layer === layer);
  const out: string[] = [];
  for (const n of nodes) {
    out.push(`#### ${n.label}`);
    out.push("");
    if (n.anchor) out.push(`\`${n.anchor}\``);
    out.push("");
    out.push(n.summary);
    if (n.reads?.length) out.push(`\n**Reads:** ${n.reads.map((r) => `\`${r}\``).join(", ")}`);
    if (n.writes?.length) out.push(`\n**Writes:** ${n.writes.map((w) => `\`${w}\``).join(", ")}`);
    if (n.invariant) out.push(`\n> **Invariant:** ${n.invariant}`);
    out.push("");
  }
  return out.join("\n");
}

const doc: string[] = [
  "<!--",
  "  GENERATED FILE — do not edit by hand.",
  "  Source: apps/web/src/architecture/spec.ts",
  "  Regenerate: cd apps/web && npm run gen:arch",
  "-->",
  "",
  "# Customer-Chat Agent — Architecture",
  "",
  "Three views of the agent under `apps/`. For the prose walkthrough, see",
  "[`customer-chat-agent.md`](customer-chat-agent.md). For an interactive version with",
  "click-to-inspect and flow highlighting, open the **Architecture** tab in the web app",
  "(`cd apps/web && npm run dev`).",
  "",
  "Dashed red edges are **early returns** — the points where the agent stops and asks",
  "instead of proceeding.",
  "",
];

for (const layer of LAYERS) {
  doc.push(`## ${layer.label}`);
  doc.push("");
  doc.push(layer.blurb);
  doc.push("");
  doc.push(mermaidFor(layer.id));
  doc.push("");
  doc.push("### Components");
  doc.push("");
  doc.push(detailsFor(layer.id));
  doc.push("");
}

mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, doc.join("\n"), "utf8");
console.log(`wrote ${OUT}`);
