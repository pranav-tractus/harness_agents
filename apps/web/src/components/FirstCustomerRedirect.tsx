import { useEffect, useState } from "react";
import { Navigate } from "react-router";
import { api } from "@/api/client";

/** Resolves `/chat` and `/graphs` to the first customer's own URL. */
export function FirstCustomerRedirect({ base }: { base: string }) {
  const [firstId, setFirstId] = useState<string | null>(null);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    api
      .listCustomers()
      .then((rows) => (rows.length > 0 ? setFirstId(rows[0].id) : setEmpty(true)))
      .catch(() => setEmpty(true));
  }, []);

  if (firstId) return <Navigate to={`${base}/${firstId}`} replace />;
  if (empty) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        No customers yet. Add one from the Chat sidebar.
      </div>
    );
  }
  return null;
}
