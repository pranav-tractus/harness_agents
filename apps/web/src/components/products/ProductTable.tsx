import { type Org, type Product } from "@/api/client";
import { BuildBadge, SourceBadge } from "@/components/graph/nodes/parts";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type Props = {
  products: Product[];
  orgs: Org[];
  showOrgColumn: boolean;
  buildingCode: string | null;
  onBuild: (p: Product) => void;
  onEdit: (p: Product) => void;
  onDelete: (p: Product) => void;
};

export function ProductTable({
  products, orgs, showOrgColumn, buildingCode, onBuild, onEdit, onDelete,
}: Props) {
  const orgName = (id: string | null) => orgs.find((o) => o.id === id)?.name ?? "—";

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Code</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Short description</TableHead>
          {showOrgColumn && <TableHead>Organization</TableHead>}
          <TableHead>Embeddings</TableHead>
          <TableHead>Source</TableHead>
          <TableHead className="w-[220px]">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {products.map((product) => (
          <TableRow key={product.id}>
            <TableCell className="font-medium">{product.code}</TableCell>
            <TableCell>{product.name ?? "—"}</TableCell>
            <TableCell>{product.short_description}</TableCell>
            {showOrgColumn && <TableCell>{orgName(product.org_id)}</TableCell>}
            <TableCell>
              <BuildBadge status={product.build_status ?? "not built"} />
            </TableCell>
            <TableCell>
              <SourceBadge label={product.source_label} />
            </TableCell>
            <TableCell>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={buildingCode === product.code}
                  onClick={() => onBuild(product)}
                >
                  {buildingCode === product.code
                    ? "Building…"
                    : product.build_status && product.build_status !== "not built"
                      ? "Rebuild"
                      : "Build Embeddings"}
                </Button>
                <Button variant="outline" size="sm" onClick={() => onEdit(product)}>
                  Edit
                </Button>
                <Button variant="destructive" size="sm" onClick={() => onDelete(product)}>
                  Delete
                </Button>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
