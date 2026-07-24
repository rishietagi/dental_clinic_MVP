"use client";

// Manage staff / dentists (6.5). Admin-only: list staff (name, email, roles,
// active), add a dentist (name + email), deactivate/reactivate. These are name-only
// records — a dentist to ASSIGN on appointments/visits and attribute in reports, not
// a login. The API is the real guard; non-admins just see a note.

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
import { useCurrentStaff } from "@/lib/use-current-staff";
import {
  createStaff,
  setStaffActive,
  useStaffList,
  type StaffMember,
} from "@/lib/use-staff";

const ROLES = ["dentist", "receptionist", "admin"] as const;

const controlClass =
  "flex rounded-md border border-input bg-transparent px-3 py-2 text-sm " +
  "shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] " +
  "focus-visible:ring-ring/50";

export function StaffSection() {
  const staffState = useCurrentStaff();
  const isAdmin = staffState.kind === "staff" && staffState.staff.roles.includes("admin");
  const list = useStaffList(true);

  if (!isAdmin) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Staff &amp; dentists</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Only an admin can manage staff.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Staff &amp; dentists</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <AddForm onAdded={() => list.kind === "ready" && list.refetch()} />

        {list.kind === "loading" && <p className="text-sm text-muted-foreground">Loading…</p>}
        {list.kind === "error" && (
          <p className="text-sm text-destructive">Couldn’t load staff: {list.message}</p>
        )}
        {list.kind === "ready" && (
          <div className="rounded-xl border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Roles</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.items.map((s) => (
                  <StaffRow key={s.id} member={s} onChanged={list.refetch} />
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AddForm({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<(typeof ROLES)[number]>("dentist");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim() || !email.trim()) {
      setError("Name and email are required.");
      return;
    }
    setBusy(true);
    const result = await createStaff({ name: name.trim(), email: email.trim(), roles: [role] });
    setBusy(false);
    if (result.status === "forbidden") {
      setError("Only an admin can add staff.");
      return;
    }
    if (result.status === "error") {
      setError(result.message);
      return;
    }
    toast.success(`${result.member.name} added`);
    setName("");
    setEmail("");
    setRole("dentist");
    onAdded();
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3 rounded-md border p-3">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Name</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Dr. Meera Prabhu" className="w-56" />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Email</label>
        <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="meera@clinic.local" className="w-56" />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Role</label>
        <select value={role} onChange={(e) => setRole(e.target.value as (typeof ROLES)[number])} className={`${controlClass} w-36`}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r[0].toUpperCase() + r.slice(1)}
            </option>
          ))}
        </select>
      </div>
      <Button type="submit" disabled={busy}>
        {busy ? "Adding…" : "Add"}
      </Button>
      {error && <p className="w-full text-sm text-destructive">{error}</p>}
    </form>
  );
}

function StaffRow({ member, onChanged }: { member: StaffMember; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);

  async function toggle() {
    setBusy(true);
    const result = await setStaffActive(member.id, !member.active);
    setBusy(false);
    if (result.status === "error") {
      toast.error(result.message);
      return;
    }
    toast.success(member.active ? `${member.name} deactivated` : `${member.name} reactivated`);
    onChanged();
  }

  return (
    <TableRow className={member.active ? "" : "opacity-60"}>
      <TableCell className="font-medium">{member.name}</TableCell>
      <TableCell className="text-muted-foreground">{member.email}</TableCell>
      <TableCell className="capitalize text-muted-foreground">{member.roles.join(", ")}</TableCell>
      <TableCell>
        <StatusPill tone={member.active ? "good" : "neutral"}>
          {member.active ? "Active" : "Inactive"}
        </StatusPill>
      </TableCell>
      <TableCell className="text-right">
        <Button variant="outline" size="sm" disabled={busy} onClick={toggle}>
          {member.active ? "Deactivate" : "Reactivate"}
        </Button>
      </TableCell>
    </TableRow>
  );
}
