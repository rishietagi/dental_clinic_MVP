"use client";

// The treatment catalogue table + admin editing.
//
// Any staff sees the list. Admin-only controls (add / edit / retire) are hidden
// for non-admins — but that is convenience, NOT security: the API rejects those
// calls with 403 regardless, and a 403 that slips through is surfaced inline.

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCurrentStaff } from "@/lib/use-current-staff";
import {
  createItem,
  formatPrice,
  setItemActive,
  updateItem,
  useTreatmentItems,
  type MutationResult,
  type TreatmentItem,
} from "@/lib/use-treatment-items";

// Turn a MutationResult into a user-facing message (null = success).
function messageFor(result: MutationResult): string | null {
  if (result === "ok") return null;
  if (result === "forbidden") return "Only an admin can change the treatment list.";
  if (result === "conflict") return "A treatment with that name already exists.";
  return result.error;
}

function AddForm({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !price.trim()) return;
    setBusy(true);
    const result = await createItem(name.trim(), price.trim());
    setBusy(false);
    const msg = messageFor(result);
    setError(msg);
    if (!msg) {
      setName("");
      setPrice("");
      onAdded();
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="new-name" className="text-xs text-muted-foreground">
            Treatment
          </label>
          <Input
            id="new-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Cleaning"
            className="w-56"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="new-price" className="text-xs text-muted-foreground">
            Default price (₹)
          </label>
          <Input
            id="new-price"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            inputMode="decimal"
            placeholder="500.00"
            className="w-32"
          />
        </div>
        <Button type="submit" size="sm" disabled={busy || !name.trim() || !price.trim()}>
          Add
        </Button>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </form>
  );
}

function Row({
  item,
  canEdit,
  onChanged,
  onError,
}: {
  item: TreatmentItem;
  canEdit: boolean;
  onChanged: () => void;
  onError: (msg: string | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(item.name);
  const [price, setPrice] = useState(item.default_price);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    const result = await updateItem(item.id, {
      name: name.trim(),
      default_price: price.trim(),
    });
    setBusy(false);
    const msg = messageFor(result);
    onError(msg);
    if (!msg) {
      setEditing(false);
      onChanged();
    }
  }

  async function toggleActive() {
    setBusy(true);
    const result = await setItemActive(item.id, !item.active);
    setBusy(false);
    onError(messageFor(result));
    onChanged();
  }

  if (editing) {
    return (
      <tr className="border-b last:border-0">
        <td className="px-3 py-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
        </td>
        <td className="px-3 py-2">
          <Input
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            inputMode="decimal"
            className="w-28"
          />
        </td>
        <td className="px-3 py-2">{item.active ? "Active" : "Retired"}</td>
        <td className="px-3 py-2">
          <div className="flex gap-1">
            <Button size="xs" onClick={save} disabled={busy}>
              Save
            </Button>
            <Button
              size="xs"
              variant="outline"
              onClick={() => {
                setName(item.name);
                setPrice(item.default_price);
                setEditing(false);
                onError(null);
              }}
              disabled={busy}
            >
              Cancel
            </Button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className={`border-b last:border-0 ${item.active ? "" : "text-muted-foreground"}`}>
      <td className="px-3 py-2 font-medium">{item.name}</td>
      <td className="px-3 py-2 tabular-nums">{formatPrice(item.default_price)}</td>
      <td className="px-3 py-2">
        {item.active ? (
          "Active"
        ) : (
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs">Retired</span>
        )}
      </td>
      <td className="px-3 py-2">
        {canEdit ? (
          <div className="flex gap-1">
            <Button size="xs" variant="outline" onClick={() => setEditing(true)} disabled={busy}>
              Edit
            </Button>
            <Button size="xs" variant="outline" onClick={toggleActive} disabled={busy}>
              {item.active ? "Retire" : "Restore"}
            </Button>
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
    </tr>
  );
}

export function TreatmentList() {
  const [includeInactive, setIncludeInactive] = useState(false);
  const state = useTreatmentItems(includeInactive);
  const staffState = useCurrentStaff();
  const [notice, setNotice] = useState<string | null>(null);

  const canEdit =
    staffState.kind === "staff" && staffState.staff.roles.includes("admin");

  return (
    <div className="flex flex-col gap-4">
      {canEdit ? (
        <AddForm onAdded={state.refetch} />
      ) : (
        staffState.kind === "staff" && (
          <p className="text-sm text-muted-foreground">
            Only an admin can change the treatment list.
          </p>
        )
      )}

      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <input
          type="checkbox"
          checked={includeInactive}
          onChange={(e) => setIncludeInactive(e.target.checked)}
        />
        Show retired treatments
      </label>

      {notice && <p className="text-sm text-destructive">{notice}</p>}

      {state.kind === "loading" && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}
      {state.kind === "error" && (
        <p className="text-sm text-destructive">
          Couldn’t load treatments: {state.message}
        </p>
      )}

      {state.kind === "ready" && (
        <>
          <p className="text-sm text-muted-foreground">
            {state.data.total} {state.data.total === 1 ? "treatment" : "treatments"}
          </p>

          {state.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No treatments yet{canEdit ? " — add the first one above." : "."}
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/50 text-left text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Treatment</th>
                    <th className="px-3 py-2 font-medium">Default price</th>
                    <th className="px-3 py-2 font-medium">State</th>
                    <th className="px-3 py-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.items.map((item) => (
                    <Row
                      key={item.id}
                      item={item}
                      canEdit={canEdit}
                      onChanged={state.refetch}
                      onError={setNotice}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
