import { useEffect, useState } from "react";
import { api, type Customer, type Profile } from "@/api/client";
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

type Props = {
  customer: Customer | null;
  onUpdated: (customer: Customer) => void;
};

const PROFILE_FIELDS: { key: keyof Profile; label: string }[] = [
  { key: "email", label: "Email" },
  { key: "phone", label: "Phone" },
  { key: "business_address", label: "Business Address" },
  { key: "delivery_address", label: "Delivery Address" },
  { key: "contact_point", label: "Contact Point" },
  { key: "approved_credit_term", label: "Approved Credit Term" },
  { key: "approved_white_label", label: "Approved White Label" },
  { key: "latest_packing_and_loading", label: "Latest Packing And Loading" },
];

function display(value: string | null) {
  return value?.trim() ? value : "—";
}

export function CustomerDetails({ customer, onUpdated }: Props) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Profile | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (customer) setDraft({ ...customer.profile });
  }, [customer]);

  if (!customer || !draft) {
    return (
      <div className="w-80 border-l p-4 text-sm text-muted-foreground">
        Select a customer to view details.
      </div>
    );
  }

  async function save() {
    if (!customer || !draft) return;
    setSaving(true);
    try {
      const updated = await api.updateProfile(customer.id, draft);
      onUpdated(updated);
      setOpen(false);
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="w-80 border-l p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Customer Details</h2>
        <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
          Edit
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-3 text-sm">
        <div>
          <div className="text-xs text-muted-foreground">Name</div>
          <div>{customer.name}</div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="text-xs text-muted-foreground">Email</div>
            <div>{display(customer.profile.email)}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Phone</div>
            <div>{display(customer.profile.phone)}</div>
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Business Address</div>
          <div>{display(customer.profile.business_address)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Delivery Address</div>
          <div>{display(customer.profile.delivery_address)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Contact Point</div>
          <div>{display(customer.profile.contact_point)}</div>
        </div>
        <div className="grid grid-cols-1 gap-3">
          <div>
            <div className="text-xs text-muted-foreground">Approved Credit Term</div>
            <div>{display(customer.profile.approved_credit_term)}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Approved White Label</div>
            <div>{display(customer.profile.approved_white_label)}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Latest Packing And Loading</div>
            <div>{display(customer.profile.latest_packing_and_loading)}</div>
          </div>
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Edit Profile — {customer.name}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            {PROFILE_FIELDS.map(({ key, label }) => (
              <div key={key} className="grid gap-1">
                <Label htmlFor={key}>{label}</Label>
                <Input
                  id={key}
                  value={draft[key] ?? ""}
                  onChange={(e) =>
                    setDraft((prev) =>
                      prev ? { ...prev, [key]: e.target.value || null } : prev,
                    )
                  }
                />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={save} disabled={saving}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
