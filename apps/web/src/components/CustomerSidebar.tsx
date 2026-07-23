import { useState } from "react";
import { type Customer } from "@/api/client";
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
import { cn } from "@/lib/utils";

type Props = {
  customers: Customer[];
  selectedId: string;
  onSelect: (id: string) => void;
  onAdd: (name: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
};

export function CustomerSidebar({ customers, selectedId, onSelect, onAdd, onDelete }: Props) {
  const [addOpen, setAddOpen] = useState(false);
  const [name, setName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Customer | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitAdd() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await onAdd(name.trim());
      setName("");
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

  return (
    <div className="flex w-56 flex-col gap-2 border-r bg-background p-3">
      <div className="flex items-center justify-between pb-1">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Customers</h2>
        <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
          Add
        </Button>
      </div>
      {customers.map((customer) => (
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

      <Dialog open={addOpen} onOpenChange={(open) => !open && setAddOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Customer</DialogTitle>
          </DialogHeader>
          <div className="grid gap-1 py-2">
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
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submitAdd} disabled={busy || !name.trim()}>
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
