"use client";

// Pricing > Consultation fee (6.7).
//
// The clinic's third charge is per-DENTIST, not a catalogue entry: the fee is a
// column on the staff record. So this tab lists the dentists with an editable
// fee rather than reusing the catalogue table.
//
// A fee of null means "not set" and reads as "—". That is deliberately distinct
// from ₹0 ("this dentist doesn't charge"): the visit screen only offers a fee
// that has actually been set, so nobody is shown a ₹0 consultation just because
// the field was never filled in.
//
// Admin-only writes, hidden here as convenience — the API is the guard (403).

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCurrentStaff } from "@/lib/use-current-staff";
import { formatPrice } from "@/lib/use-treatment-items";
import { updateStaff, useStaffList, type StaffMember } from "@/lib/use-staff";

function Row({
  member,
  canEdit,
  onChanged,
}: {
  member: StaffMember;
  canEdit: boolean;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [fee, setFee] = useState(member.consultation_fee ?? "");
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    // An empty box clears the fee back to "not set" (null), rather than
    // writing a 0 the receptionist never intended.
    const trimmed = fee.trim();
    const result = await updateStaff(member.id, {
      consultation_fee: trimmed === "" ? null : trimmed,
    });
    setBusy(false);

    if (result.status === "ok") {
      setEditing(false);
      toast.success(`Updated ${member.name}’s consultation fee.`);
      onChanged();
      return;
    }
    toast.error(
      result.status === "forbidden"
        ? "Only an admin can change consultation fees."
        : result.message,
    );
  }

  if (editing) {
    return (
      <tr className="border-b last:border-0">
        <td className="px-3 py-2 font-medium">{member.name}</td>
        <td className="px-3 py-2">
          <Input
            value={fee}
            onChange={(e) => setFee(e.target.value)}
            inputMode="decimal"
            placeholder="Leave blank for none"
            className="w-40"
          />
        </td>
        <td className="px-3 py-2">
          <div className="flex gap-1">
            <Button size="xs" onClick={save} disabled={busy}>
              Save
            </Button>
            <Button
              size="xs"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setFee(member.consultation_fee ?? "");
                setEditing(false);
              }}
            >
              Cancel
            </Button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b last:border-0">
      <td className="px-3 py-2 font-medium">{member.name}</td>
      <td className="px-3 py-2 tabular-nums">
        {member.consultation_fee === null ? (
          <span className="text-muted-foreground">— not set</span>
        ) : (
          formatPrice(member.consultation_fee)
        )}
      </td>
      <td className="px-3 py-2">
        {canEdit ? (
          <Button size="xs" variant="outline" onClick={() => setEditing(true)}>
            {member.consultation_fee === null ? "Set fee" : "Edit"}
          </Button>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
    </tr>
  );
}

export function ConsultationFees() {
  // Active dentists only: a retired dentist can't be picked on a visit, so
  // there's nothing to price.
  const state = useStaffList(false);
  const staffState = useCurrentStaff();

  const canEdit =
    staffState.kind === "staff" && staffState.staff.roles.includes("admin");

  const dentists =
    state.kind === "ready"
      ? state.items.filter((m) => m.roles.includes("dentist"))
      : [];

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        What each dentist charges for a consultation. When you record a visit,
        the fee for that visit’s dentist is offered as a line you can add to the
        bill — it is never added automatically.
      </p>

      {!canEdit && staffState.kind === "staff" && (
        <p className="text-sm text-muted-foreground">
          Only an admin can change consultation fees.
        </p>
      )}

      {state.kind === "loading" && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}
      {state.kind === "error" && (
        <p className="text-sm text-destructive">
          Couldn’t load dentists: {state.message}
        </p>
      )}

      {state.kind === "ready" &&
        (dentists.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No dentists yet — add them under Settings → Clinic.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/50 text-left text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Dentist</th>
                  <th className="px-3 py-2 font-medium">Consultation fee</th>
                  <th className="px-3 py-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {dentists.map((m) => (
                  <Row
                    key={m.id}
                    member={m}
                    canEdit={canEdit}
                    onChanged={state.refetch}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </div>
  );
}
