import { useState } from "react";
import { type Customer, type Org } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
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
import { cn } from "@/lib/utils";

type Props = {
  customers: Customer[];
  orgs: Org[];
  selectedId: string;
  onSelect: (id: string) => void;
  onAdd: (name: string, orgId: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
};

export function CustomerSidebar({ customers, orgs, selectedId, onSelect, onAdd, onDelete }: Props) {
  const [addOpen, setAddOpen] = useState(false);
  const [name, setName] = useState("");
  const [orgId, setOrgId] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Customer | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitAdd() {
    if (!name.trim() || !orgId) return;
    setBusy(true);
    try {
      await onAdd(name.trim(), orgId);
      setName("");
      setOrgId("");
      setAddOpen(false);
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setBusy(true);
    try {
      await onDelete(deleteTarget.id);
      setDeleteTarget(null);
    } finally {
      setBusy(false);
    }
  }

  const groups = orgs
    .map((o) => ({
      key: o.id,
      label: o.name,
      rows: customers.filter((c) => c.org_id === o.id),
    }))
    .filter((g) => g.rows.length > 0);
  const orphans = customers.filter((c) => !orgs.some((o) => o.id === c.org_id));
  if (orphans.length > 0) groups.push({ key: "none", label: "Unassigned", rows: orphans });

  return (
    <div className="flex w-56 flex-col gap-2 border-r bg-background p-3">
      <div className="flex items-center justify-between pb-1">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Customers</h2>
        <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
          Add
        </Button>
      </div>
      {groups.map((group) => (
        <div key={group.key} role="group" aria-label={group.label} className="grid gap-2">
          <h3 className="px-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {group.label}
          </h3>
          {group.rows.map((customer) => (
            <Card
              key={customer.id}
              className={cn(
                "cursor-pointer transition-colors hover:bg-muted/50",
                selectedId === customer.id && "border-primary/60 bg-accent/40",
              )}
              onClick={() => onSelect(customer.id)}
            >
              <CardHeader className="p-3">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-sm font-medium">{customer.name}</CardTitle>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs text-muted-foreground hover:text-destructive"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteTarget(customer);
                    }}
                  >
                    ✕
                  </Button>
                </div>
              </CardHeader>
            </Card>
          ))}
        </div>
      ))}

      <Dialog open={addOpen} onOpenChange={(open) => !open && setAddOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Customer</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-1">
              <Label htmlFor="customer-org">Organization</Label>
              <Select value={orgId} onValueChange={(v) => v && setOrgId(v)}>
                <SelectTrigger id="customer-org" aria-label="Organization">
                  <SelectValue placeholder="Select an organization" />
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
              <Label htmlFor="customer-name">Name</Label>
              <Input
                id="customer-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") submitAdd();
                }}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submitAdd} disabled={busy || !name.trim() || !orgId}>
              Add
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {deleteTarget?.name}?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This permanently removes the customer and all of their messages and summaries.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
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
