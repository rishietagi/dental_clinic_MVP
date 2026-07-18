"use client";

// Role-aware navigation. It fetches the signed-in staff member's roles from the
// backend (/me) and shows only the nav items their roles permit.
//
// IMPORTANT: this is a convenience, not a security boundary. Hiding a link is
// not access control — the backend enforces roles on every endpoint (a hidden
// button is not security). The pages themselves don't exist yet (Phase 2+);
// these items demonstrate the gating.

import { LayoutDashboard, BarChart3, Shield } from "lucide-react";

import { useCurrentStaff } from "@/lib/use-current-staff";

type NavItem = {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  // Which roles may see this item. undefined = any signed-in staff member.
  anyOf?: string[];
};

const NAV: NavItem[] = [
  { label: "Dashboard", icon: LayoutDashboard },
  { label: "Reports", icon: BarChart3, anyOf: ["dentist", "admin"] },
  { label: "Admin", icon: Shield, anyOf: ["admin"] },
];

export function RoleNav() {
  const state = useCurrentStaff();

  if (state.kind === "loading") {
    return <p className="text-sm text-muted-foreground">Loading your access…</p>;
  }

  if (state.kind === "not-staff") {
    return (
      <p className="text-sm text-destructive">
        Your account isn’t set up as clinic staff yet. Ask an admin to add you.
      </p>
    );
  }

  if (state.kind === "error") {
    return <p className="text-sm text-destructive">Couldn’t load your access: {state.message}</p>;
  }

  const roles = state.staff.roles;
  const has = (item: NavItem) => !item.anyOf || item.anyOf.some((r) => roles.includes(r));
  const visible = NAV.filter(has);

  return (
    <div className="flex w-full max-w-sm flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        Roles: {roles.length ? roles.join(", ") : "none"}
      </p>
      <nav className="flex flex-col gap-1">
        {visible.map(({ label, icon: Icon }) => (
          <span
            key={label}
            className="flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-accent"
          >
            <Icon className="size-4" />
            {label}
          </span>
        ))}
      </nav>
    </div>
  );
}
