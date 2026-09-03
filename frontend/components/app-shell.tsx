"use client";

import { useState } from "react";

// The app shell (6.2, reworked to a LEFT SIDEBAR in 6.3): a persistent vertical
// nav rail — clinic name at the top, nav below — with the page content filling
// the rest of the width. On small screens the sidebar collapses behind a menu.
//
// Nothing sits at the bottom any more: the Sign out button went with the login
// (10.1) and the theme toggle went when the app was pinned to light (10.6).
//
// `anyOf` role filtering is kept on the remaining items: roles still exist on the
// staff row, they are simply never refused (see backend app/auth.py).

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CalendarDays,
  FlaskConical,
  LayoutDashboard,
  Menu,
  Receipt,
  Settings,
  Shield,
  Users,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useClinicSettings } from "@/lib/use-clinic-settings";
import { useCurrentStaff } from "@/lib/use-current-staff";
import { cn } from "@/lib/utils";

type NavItem = {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  anyOf?: string[]; // roles that may see it; undefined = any signed-in staff
};

const NAV: NavItem[] = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Patients", href: "/patients", icon: Users },
  { label: "Calendar", href: "/calendar", icon: CalendarDays },
  { label: "Invoices", href: "/invoices", icon: Receipt },
  { label: "Lab", href: "/lab", icon: FlaskConical },
  // HIDDEN in 10.2. The app now runs on one shared PC at the front desk, so a
  // role gate cannot keep the practice's revenue private — whoever is sitting
  // there is "signed in". The Reports API and its tests are untouched; only the
  // way in is removed. Uncomment this line to bring the page back.
  // { label: "Reports", href: "/reports", icon: BarChart3, anyOf: ["admin"] },
  // Renamed "Treatments" -> "Pricing" in 6.7: the screen now covers treatments,
  // medicines, and per-dentist consultation fees. The route is unchanged.
  { label: "Pricing", href: "/settings/treatments", icon: Shield, anyOf: ["admin"] },
  { label: "Settings", href: "/settings/clinic", icon: Settings, anyOf: ["admin"] },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-full">
      {/* Mobile top bar */}
      <div className="fixed inset-x-0 top-0 z-30 flex items-center gap-3 border-b bg-sidebar px-4 py-2.5 md:hidden">
        <Button variant="ghost" size="sm" className="px-2" onClick={() => setMobileOpen(true)} aria-label="Open menu">
          <Menu className="size-5" />
        </Button>
        <Brand />
      </div>

      {/* Sidebar — fixed on desktop, a slide-over on mobile */}
      <Sidebar
        pathname={pathname}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
      />

      {/* Content: offset by the sidebar width on desktop, by the top bar on mobile.
          Keyed by pathname so the fade-in replays on navigation. */}
      <div className="flex min-h-full flex-1 flex-col md:pl-60">
        <main key={pathname} className="page-enter mx-auto w-full max-w-6xl flex-1 px-5 pb-10 pt-16 md:px-8 md:pt-8">
          {children}
        </main>
      </div>
    </div>
  );
}

function Brand() {
  const { settings } = useClinicSettings();
  return (
    <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-tight">
      <Image
        src="/clinic-logo.png"
        alt=""
        width={40}
        height={30}
        priority
        className="h-9 w-auto object-contain"
      />
      <span className="truncate text-[15px] leading-tight">
        {settings.clinic_name || "Dental Clinic"}
      </span>
    </Link>
  );
}

function Sidebar({
  pathname,
  mobileOpen,
  onClose,
}: {
  pathname: string;
  mobileOpen: boolean;
  onClose: () => void;
}) {
  const staffState = useCurrentStaff();
  const roles = staffState.kind === "staff" ? staffState.staff.roles : [];
  const canSee = (item: NavItem) => !item.anyOf || item.anyOf.some((r) => roles.includes(r));

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(href + "/");

  return (
    <>
      {/* Mobile scrim */}
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close menu"
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r bg-sidebar transition-transform md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center justify-between px-4 py-4">
          <Brand />
          <Button variant="ghost" size="sm" className="px-2 md:hidden" onClick={onClose} aria-label="Close menu">
            <X className="size-5" />
          </Button>
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3 py-2">
          {NAV.filter(canSee).map(({ label, href, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={onClose}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                isActive(href)
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon className="size-4 shrink-0" />
              <span>{label}</span>
            </Link>
          ))}
        </nav>

        {/* The sidebar footer is gone: the Sign out button went with the login
            screen (10.1), and the theme toggle went when the app was pinned to
            light (10.6). Nothing is left to put here, so there is no empty bar. */}
      </aside>
    </>
  );
}


