import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";
import { toast } from "sonner";
import { api, type Org, type Product } from "@/api/client";
import {
  ProductFormDialog,
  type ProductFormValues,
} from "@/components/products/ProductFormDialog";
import { ProductTable } from "@/components/products/ProductTable";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function ProductsPage() {
  const { orgId } = useParams();
  const [products, setProducts] = useState<Product[]>([]);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [sourceFilter, setSourceFilter] = useState("all");
  const [editProduct, setEditProduct] = useState<Product | null>(null);
  const [deleteProduct, setDeleteProduct] = useState<Product | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [buildingCode, setBuildingCode] = useState<string | null>(null);

  const visibleProducts =
    sourceFilter === "all" ? products : products.filter((p) => p.source_label === sourceFilter);
  const currentOrg = orgs.find((o) => o.id === orgId) ?? null;
  const defaultOrgId = orgId ?? orgs[0]?.id ?? "";

  const loadProducts = useCallback(async () => {
    setProducts(await api.listProducts(orgId));
  }, [orgId]);

  useEffect(() => {
    loadProducts().catch(console.error);
  }, [loadProducts]);

  useEffect(() => {
    api.listOrgs().then(setOrgs).catch(console.error);
  }, []);

  async function saveNew(values: ProductFormValues) {
    setSaving(true);
    try {
      await api.createProduct(values);
      setAddOpen(false);
      await loadProducts();
      toast.success("Product added");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add product");
    } finally {
      setSaving(false);
    }
  }

  async function saveEdit(values: ProductFormValues) {
    if (!editProduct) return;
    setSaving(true);
    try {
      await api.updateProduct(editProduct.id, {
        name: values.name,
        short_description: values.short_description,
        long_description: values.long_description,
        spec: values.spec,
        metadata: values.metadata,
        org_id: values.org_id,
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

  async function buildEmbeddings(product: Product) {
    setBuildingCode(product.code);
    try {
      await api.buildProduct(product.id);
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
        <h1 className="text-xl font-semibold">
          {currentOrg ? `${currentOrg.name} — Products` : "Products"}
        </h1>
        <div className="flex items-center gap-3">
          <Select value={sourceFilter} onValueChange={(v) => v && setSourceFilter(v)}>
            <SelectTrigger id="source-filter" aria-label="Source" className="w-[160px]">
              <SelectValue placeholder="Source" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sources</SelectItem>
              <SelectItem value="OG Files">OG Files</SelectItem>
              <SelectItem value="Test Files">Test Files</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={() => setAddOpen(true)} disabled={orgs.length === 0}>
            Add Product
          </Button>
        </div>
      </div>

      <ProductTable
        products={visibleProducts}
        orgs={orgs}
        showOrgColumn={!orgId}
        buildingCode={buildingCode}
        onBuild={buildEmbeddings}
        onEdit={setEditProduct}
        onDelete={setDeleteProduct}
      />

      <ProductFormDialog
        open={addOpen}
        mode="add"
        product={null}
        orgs={orgs}
        defaultOrgId={defaultOrgId}
        saving={saving}
        onCancel={() => setAddOpen(false)}
        onSubmit={saveNew}
      />

      <ProductFormDialog
        open={!!editProduct}
        mode="edit"
        product={editProduct}
        orgs={orgs}
        defaultOrgId={defaultOrgId}
        saving={saving}
        onCancel={() => setEditProduct(null)}
        onSubmit={saveEdit}
      />

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
