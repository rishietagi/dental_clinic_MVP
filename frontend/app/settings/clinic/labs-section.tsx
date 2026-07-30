"use client";

// Manage labs (6.6). Admin-only: the list of outside labs the clinic sends work to,
// with add + deactivate. Deactivating retires a lab from the picker while keeping
// old cases readable — the same rule as treatment items and staff.

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { StatusPill } from "@/components/ui/status-pill";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { createLab, setLabActive, useLabs, type LabVendor } from "@/lib/use-labs";
import { useCurrentStaff } from "@/lib/use-current-staff";

export function LabsSection() {
  const staffState = useCurrentStaff();
  const isAdmin = staffState.kind === "staff" && staffState.staff.roles.includes("admin");
  const labs = useLabs(true); // include inactive so they can be reactivated

  if (!isAdmin) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Labs</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Only an admin can manage labs.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Labs</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <AddLabForm onAdded={labs.refetch} />

        {labs.kind === "loading" && <p className="text-sm text-muted-foreground">Loading…</p>}
        {labs.kind === "error" && (
          <p className="text-sm text-destructive">Couldn’t load labs: {labs.message}</p>
        )}
        {labs.kind === "ready" && labs.items.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No labs yet. Add the labs this clinic sends work to.
          </p>
        )}
        {labs.kind === "ready" && labs.items.length > 0 && (
          <div className="rounded-xl border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Lab</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {labs.items.map((l) => (
                  <LabRow key={l.id} lab={l} onChanged={labs.refetch} />
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AddLabForm({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("The lab needs a name.");
      return;
    }
    setBusy(true);
    const result = await createLab({
      name: name.trim(),
      phone: phone.trim() || undefined,
      address: address.trim() || undefined,
    });
    setBusy(false);
    if (result.status === "forbidden") {
      setError("Only an admin can add labs.");
      return;
    }
    if (result.status === "error") {
      setError(result.message);
      return;
    }
    toast.success(`${result.lab.name} added`);
    setName("");
    setPhone("");
    setAddress("");
    onAdded();
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3 rounded-md border p-3">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Lab name</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Sri Dental Lab" className="w-52" />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Phone</label>
        <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="98800 00000" className="w-40" />
      </div>
      <div className="flex flex-1 flex-col gap-1">
        <label className="text-xs text-muted-foreground">Address (optional)</label>
        <Input value={address} onChange={(e) => setAddress(e.target.value)} />
      </div>
      <Button type="submit" disabled={busy}>
        {busy ? "Adding…" : "Add lab"}
      </Button>
      {error && <p className="w-full text-sm text-destructive">{error}</p>}
    </form>
  );
}

function LabRow({ lab, onChanged }: { lab: LabVendor; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);

  async function toggle() {
    setBusy(true);
    const result = await setLabActive(lab.id, !lab.active);
    setBusy(false);
    if (result.status === "error") {
      toast.error(result.message);
      return;
    }
    toast.success(lab.active ? `${lab.name} retired` : `${lab.name} reactivated`);
    onChanged();
  }

  return (
    <TableRow className={lab.active ? "" : "opacity-60"}>
      <TableCell className="font-medium">{lab.name}</TableCell>
      <TableCell className="text-muted-foreground">{lab.phone ?? "—"}</TableCell>
      <TableCell>
        <StatusPill tone={lab.active ? "good" : "neutral"}>
          {lab.active ? "Active" : "Retired"}
        </StatusPill>
      </TableCell>
      <TableCell className="text-right">
        <Button variant="outline" size="sm" disabled={busy} onClick={toggle}>
          {lab.active ? "Retire" : "Reactivate"}
        </Button>
      </TableCell>
    </TableRow>
  );
}
