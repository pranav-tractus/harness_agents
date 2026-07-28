import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, type Product } from "@/api/client";
import { Button } from "@/components/ui/button";
import { BuildBadge } from "@/components/graph/nodes/parts";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type MetaRow = { id: string; key: string; value: string };

function MetaEditor({
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
      <Button variant="outline" size="sm" onClick={() => setRows([...rows, { id: `new-${Date.now()}`, key: "", value: "" }])}>
        Add metadata field
      </Button>
    </div>
  );
}

export function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [editProduct, setEditProduct] = useState<Product | null>(null);
  const [deleteProduct, setDeleteProduct] = useState<Product | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newSpec, setNewSpec] = useState("");
  const [description, setDescription] = useState("");
  const [spec, setSpec] = useState("");
  const [saving, setSaving] = useState(false);
  const [buildingCode, setBuildingCode] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [longDescription, setLongDescription] = useState("");
  const [metaRows, setMetaRows] = useState<MetaRow[]>([]);
  const [newName, setNewName] = useState("");
  const [newLongDescription, setNewLongDescription] = useState("");
  const [newMetaRows, setNewMetaRows] = useState<MetaRow[]>([]);

  function rowsToMeta(rows: MetaRow[]): Record<string, string> {
    const out: Record<string, string> = {};
    for (const r of rows) {
      const k = r.key.trim();
      if (k) out[k] = r.value;
    }
    return out;
  }

  function metaToRows(meta: Record<string, string>): MetaRow[] {
    return Object.entries(meta ?? {}).map(([key, value]) => ({ id: `meta-${key}`, key, value }));
  }

  async function loadProducts() {
    const rows = await api.listProducts();
    setProducts(rows);
  }

  useEffect(() => {
    loadProducts().catch(console.error);
  }, []);

  function openEdit(product: Product) {
    setEditProduct(product);
    setName(product.name ?? "");
    setDescription(product.short_description);
    setLongDescription(product.long_description ?? "");
    setSpec(product.spec ?? "");
    setMetaRows(metaToRows(product.metadata));
  }

  async function saveEdit() {
    if (!editProduct) return;
    setSaving(true);
    try {
      await api.updateProduct(editProduct.id, {
        name: name.trim() || null,
        short_description: description,
        long_description: longDescription.trim() || null,
        spec: spec.trim() || null,
        metadata: rowsToMeta(metaRows),
      });
      setEditProduct(null);
      await loadProducts();
      toast.success("Product updated");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update product");
    } finally {
      setSaving(false);
    }
  }

  async function saveNew() {
    if (!newCode.trim() || !newDescription.trim()) return;
    setSaving(true);
    try {
      await api.createProduct({
        code: newCode.trim(),
        name: newName.trim() || null,
        short_description: newDescription.trim(),
        long_description: newLongDescription.trim() || null,
        spec: newSpec.trim() || null,
        metadata: rowsToMeta(newMetaRows),
      });
      setAddOpen(false);
      setNewCode("");
      setNewDescription("");
      setNewSpec("");
      setNewName("");
      setNewLongDescription("");
      setNewMetaRows([]);
      await loadProducts();
      toast.success("Product added");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add product");
    } finally {
      setSaving(false);
    }
  }

  async function buildEmbeddings(product: Product) {
    setBuildingCode(product.code);
    try {
      await api.buildProduct(product.code);
      await loadProducts();
      toast.success(`Built embeddings for ${product.code}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to build embeddings");
    } finally {
      setBuildingCode(null);
    }
  }

  async function confirmDelete() {
    if (!deleteProduct) return;
    setSaving(true);
    try {
      await api.deleteProduct(deleteProduct.id);
      setDeleteProduct(null);
      await loadProducts();
      toast.success(`Deleted ${deleteProduct.code}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete product");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Products</h1>
        <Button onClick={() => setAddOpen(true)}>Add Product</Button>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Code</TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Short description</TableHead>
            <TableHead>Embeddings</TableHead>
            <TableHead className="w-[220px]">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {products.map((product) => (
            <TableRow key={product.id}>
              <TableCell className="font-medium">{product.code}</TableCell>
              <TableCell>{product.name ?? "—"}</TableCell>
              <TableCell>{product.short_description}</TableCell>
              <TableCell>
                <BuildBadge status={product.build_status ?? "not built"} />
              </TableCell>
              <TableCell>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={buildingCode === product.code}
                    onClick={() => buildEmbeddings(product)}
                  >
                    {buildingCode === product.code
                      ? "Building…"
                      : product.build_status && product.build_status !== "not built"
                        ? "Rebuild"
                        : "Build Embeddings"}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => openEdit(product)}>
                    Edit
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => setDeleteProduct(product)}
                  >
                    Delete
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Dialog open={addOpen} onOpenChange={(open) => !open && setAddOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Product</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-1">
              <Label htmlFor="new-code">Code</Label>
              <Input
                id="new-code"
                value={newCode}
                onChange={(e) => setNewCode(e.target.value)}
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="new-name">Name</Label>
              <Input id="new-name" value={newName} onChange={(e) => setNewName(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="new-description">Short description</Label>
              <Textarea
                id="new-description"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="new-long">Long description</Label>
              <Textarea id="new-long" value={newLongDescription}
                onChange={(e) => setNewLongDescription(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label>Metadata</Label>
              <MetaEditor rows={newMetaRows} setRows={setNewMetaRows} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="new-spec">Spec</Label>
              <Textarea
                id="new-spec"
                value={newSpec}
                onChange={(e) => setNewSpec(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={saveNew}
              disabled={saving || !newCode.trim() || !newDescription.trim()}
            >
              Add
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!editProduct} onOpenChange={(open) => !open && setEditProduct(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Product</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-1">
              <Label>Code</Label>
              <Input value={editProduct?.code ?? ""} readOnly disabled />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="edit-name">Name</Label>
              <Input id="edit-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="description">Short description</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="long">Long description</Label>
              <Textarea id="long" value={longDescription}
                onChange={(e) => setLongDescription(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label>Metadata</Label>
              <MetaEditor rows={metaRows} setRows={setMetaRows} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="spec">Spec</Label>
              <Textarea id="spec" value={spec} onChange={(e) => setSpec(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditProduct(null)}>
              Cancel
            </Button>
            <Button onClick={saveEdit} disabled={saving}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteProduct} onOpenChange={(open) => !open && setDeleteProduct(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {deleteProduct?.code}?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This will permanently remove the product from the catalog.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteProduct(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={saving}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
