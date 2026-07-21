import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, type Product } from "@/api/client";
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
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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

  async function loadProducts() {
    const rows = await api.listProducts();
    setProducts(rows);
  }

  useEffect(() => {
    loadProducts().catch(console.error);
  }, []);

  function openEdit(product: Product) {
    setEditProduct(product);
    setDescription(product.description);
    setSpec(product.spec ?? "");
  }

  async function saveEdit() {
    if (!editProduct) return;
    setSaving(true);
    try {
      await api.updateProduct(editProduct.id, {
        description,
        spec: spec.trim() || null,
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
        description: newDescription.trim(),
        spec: newSpec.trim() || null,
      });
      setAddOpen(false);
      setNewCode("");
      setNewDescription("");
      setNewSpec("");
      await loadProducts();
      toast.success("Product added");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add product");
    } finally {
      setSaving(false);
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
            <TableHead>Description</TableHead>
            <TableHead>Spec</TableHead>
            <TableHead className="w-[140px]">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {products.map((product) => (
            <TableRow key={product.id}>
              <TableCell className="font-medium">{product.code}</TableCell>
              <TableCell>{product.description}</TableCell>
              <TableCell>{product.spec ?? "—"}</TableCell>
              <TableCell>
                <div className="flex gap-2">
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
              <Label htmlFor="new-description">Description</Label>
              <Textarea
                id="new-description"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
              />
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
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
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
