import { useEffect, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { api, type Org } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function OrgsPage() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<Org | null>(null);
  const [deleting, setDeleting] = useState<Org | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [tagline, setTagline] = useState("");
  const [busy, setBusy] = useState(false);
  const [buildingId, setBuildingId] = useState<string | null>(null);

  async function load() {
    setOrgs(await api.listOrgs());
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  function openAdd() {
    setName("");
    setTagline("");
    setAddOpen(true);
  }

  function openEdit(org: Org) {
    setName(org.name);
    setTagline(org.tagline ?? "");
    setEditing(org);
  }

  async function submitAdd() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.createOrg(name.trim(), tagline.trim());
      setAddOpen(false);
      await load();
      toast.success("Organization added");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add organization");
    } finally {
      setBusy(false);
    }
  }

  async function submitEdit() {
    if (!editing || !name.trim()) return;
    setBusy(true);
    try {
      await api.updateOrg(editing.id, { name: name.trim(), tagline: tagline.trim() });
      setEditing(null);
      await load();
      toast.success("Organization updated");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update organization");
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    setBusy(true);
    setDeleteError(null);
    try {
      await api.deleteOrg(deleting.id);
      setDeleting(null);
      await load();
      toast.success("Organization deleted");
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete organization");
    } finally {
      setBusy(false);
    }
  }

  async function build(org: Org) {
    setBuildingId(org.id);
    try {
      await api.buildOrg(org.id);
      await load();
      toast.success(`Built embeddings for ${org.name}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to build embeddings");
    } finally {
      setBuildingId(null);
    }
  }

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Organizations</h1>
        <Button onClick={openAdd}>Add Organization</Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {orgs.map((org) => (
          <Card key={org.id} data-org-card>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-2">
                <CardTitle className="text-base">{org.name}</CardTitle>
                {org.is_catchall && <Badge variant="outline">catch-all</Badge>}
              </div>
              <p className="text-xs text-muted-foreground">{org.tagline ?? "—"}</p>
            </CardHeader>
            <CardContent className="grid gap-3">
              <div className="text-sm text-muted-foreground">
                {org.product_count} products · {org.customer_count} customers
              </div>
              <div className="text-xs">
                {org.unbuilt_count === 0 ? (
                  <span className="text-emerald-600">all embeddings built</span>
                ) : (
                  <span className="text-amber-600">
                    {org.unbuilt_count} of {org.product_count} need embedding
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {!org.is_catchall && (
                  <Link
                    to={`/orgs/${org.id}/products`}
                    className={buttonVariants({ variant: "outline", size: "sm" })}
                  >
                    View catalog
                  </Link>
                )}
                {!org.is_catchall && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={buildingId === org.id || org.product_count === 0}
                    onClick={() => build(org)}
                  >
                    {buildingId === org.id ? "Building…" : "Build"}
                  </Button>
                )}
                <Button variant="outline" size="sm" onClick={() => openEdit(org)}>
                  Edit
                </Button>
                {!org.is_catchall && (
                  <Button
                    data-delete
                    variant="destructive"
                    size="sm"
                    onClick={() => {
                      setDeleteError(null);
                      setDeleting(org);
                    }}
                  >
                    Delete
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog
        open={addOpen || !!editing}
        onOpenChange={(open) => {
          if (!open) {
            setAddOpen(false);
            setEditing(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "Edit Organization" : "Add Organization"}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-1">
              <Label htmlFor="org-name">Name</Label>
              <Input id="org-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="org-tagline">Tagline</Label>
              <Input
                id="org-tagline"
                value={tagline}
                onChange={(e) => setTagline(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setAddOpen(false);
                setEditing(null);
              }}
            >
              Cancel
            </Button>
            <Button onClick={editing ? submitEdit : submitAdd} disabled={busy || !name.trim()}>
              {editing ? "Save" : "Add"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {deleting?.name}?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            An organization can only be deleted once its products and customers have been
            moved elsewhere.
          </p>
          {deleteError && <p className="text-sm text-destructive">{deleteError}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={busy}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
