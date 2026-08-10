import { useEffect, useState } from "react";
import { type Org, type Product } from "@/api/client";
import {
  MetaEditor,
  metaToRows,
  rowsToMeta,
  type MetaRow,
} from "@/components/products/MetaEditor";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

export type ProductFormValues = {
  code: string;
  name: string | null;
  short_description: string;
  long_description: string | null;
  spec: string | null;
  metadata: Record<string, string>;
  org_id: string;
};

type Props = {
  open: boolean;
  mode: "add" | "edit";
  product: Product | null;
  orgs: Org[];
  defaultOrgId: string;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (values: ProductFormValues) => void;
};

export function ProductFormDialog({
  open, mode, product, orgs, defaultOrgId, saving, onCancel, onSubmit,
}: Props) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [shortDescription, setShortDescription] = useState("");
  const [longDescription, setLongDescription] = useState("");
  const [spec, setSpec] = useState("");
  const [orgId, setOrgId] = useState(defaultOrgId);
  const [metaRows, setMetaRows] = useState<MetaRow[]>([]);

  useEffect(() => {
    if (!open) return;
    setCode(product?.code ?? "");
    setName(product?.name ?? "");
    setShortDescription(product?.short_description ?? "");
    setLongDescription(product?.long_description ?? "");
    setSpec(product?.spec ?? "");
    setOrgId(product?.org_id ?? defaultOrgId);
    setMetaRows(metaToRows(product?.metadata ?? {}));
  }, [open, product, defaultOrgId]);

  const canSubmit =
    !!orgId && !!shortDescription.trim() && (mode === "edit" || !!code.trim());

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === "edit" ? "Edit Product" : "Add Product"}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 py-2">
          <div className="grid gap-1">
            <Label htmlFor="product-code">Code</Label>
            <Input
              id="product-code"
              value={code}
              readOnly={mode === "edit"}
              disabled={mode === "edit"}
              onChange={(e) => setCode(e.target.value)}
            />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="product-org">Organization</Label>
            <Select value={orgId} onValueChange={(v) => v && setOrgId(v)}>
              <SelectTrigger id="product-org" aria-label="Organization">
                <SelectValue placeholder="Organization" />
              </SelectTrigger>
              <SelectContent>
                {orgs.map((o) => (
                  <SelectItem key={o.id} value={o.id}>
                    {o.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1">
            <Label htmlFor="product-name">Name</Label>
            <Input id="product-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="product-short">Short description</Label>
            <Textarea
              id="product-short"
              value={shortDescription}
              onChange={(e) => setShortDescription(e.target.value)}
            />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="product-long">Long description</Label>
            <Textarea
              id="product-long"
              value={longDescription}
              onChange={(e) => setLongDescription(e.target.value)}
            />
          </div>
          <div className="grid gap-1">
            <Label>Metadata</Label>
            <MetaEditor rows={metaRows} setRows={setMetaRows} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="product-spec">Spec</Label>
            <Textarea id="product-spec" value={spec} onChange={(e) => setSpec(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            disabled={saving || !canSubmit}
            onClick={() =>
              onSubmit({
                code: code.trim(),
                name: name.trim() || null,
                short_description: shortDescription.trim(),
                long_description: longDescription.trim() || null,
                spec: spec.trim() || null,
                metadata: rowsToMeta(metaRows),
                org_id: orgId,
              })
            }
          >
            {mode === "edit" ? "Save" : "Add"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
