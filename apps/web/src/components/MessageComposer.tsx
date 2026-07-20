import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

type Props = {
  role: "seller" | "customer";
  onRoleChange: (r: "seller" | "customer") => void;
  onMessage: (body: string) => void;
  onAskAgent: () => void;
  onApprove: () => void;
  showApprove: boolean;
};

export function MessageComposer({ role, onRoleChange, onMessage, onAskAgent, onApprove, showApprove }: Props) {
  const [text, setText] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    onMessage(value);
    setText("");
  }

  return (
    <form data-testid="composer-form" onSubmit={submit}
      className="flex items-center gap-2 border-t bg-card px-4 py-3">
      <ToggleGroup value={[role]} onValueChange={(v) => { const n = v[0]; if (n) onRoleChange(n as "seller" | "customer"); }}>
        <ToggleGroupItem value="seller" className="text-xs font-medium">Seller</ToggleGroupItem>
        <ToggleGroupItem value="customer" className="text-xs font-medium">Customer</ToggleGroupItem>
      </ToggleGroup>
      <Input value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Message…" className="flex-1" />
      <Button type="submit" size="sm" variant="secondary">Send</Button>
      <Button type="button" size="sm" onClick={onAskAgent}>Ask agent</Button>
      {showApprove && <Button type="button" size="sm" variant="outline" onClick={onApprove}>Approve</Button>}
    </form>
  );
}
