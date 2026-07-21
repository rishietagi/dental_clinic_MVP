"use client";

// The app shell (step 6.2): a persistent top header — clinic name, role-aware
// horizontal nav with an active-route highlight, a theme toggle, and sign-out —
// over a centered content column. Before this, nav only existed on the dashboard
// and every page rolled its own <main>; now every signed-in page shares one frame.
//
// /login opts out (it has its own centered card and no session yet), detected by
// pathname — the shell renders children bare there.

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  CalendarDays,
  LayoutDashboard,
  Moon,
  Settings,
  Shield,
  Sun,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";
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
  { label: "Reports", href: "/reports", icon: BarChart3, anyOf: ["dentist", "admin"] },
  { label: "Treatments", href: "/settings/treatments", icon: Shield, anyOf: ["admin"] },
  { label: "Settings", href: "/settings/clinic", icon: Settings, anyOf: ["admin"] },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // /login (and any future bare route) renders without the shell.
  if (pathname === "/login") {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-full flex-col">
      <Header pathname={pathname} />
      <main className="mx-auto w-full max-w-4xl flex-1 px-5 py-8">{children}</main>
    </div>
  );
}

function Header({ pathname }: { pathname: string }) {
  const { settings } = useClinicSettings();
  const staffState = useCurrentStaff();
  const roles = staffState.kind === "staff" ? staffState.staff.roles : [];
  const canSee = (item: NavItem) => !item.anyOf || item.anyOf.some((r) => roles.includes(r));

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(href + "/");

  return (
    <header className="sticky top-0 z-20 border-b bg-sidebar/85 backdrop-blur">
      <div className="mx-auto flex w-full max-w-4xl items-center gap-4 px-5 py-3">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground text-xs font-bold">
            {(settings.clinic_name || "DC").slice(0, 2).toUpperCase()}
          </span>
          <span className="hidden sm:inline">{settings.clinic_name || "Dental Clinic"}</span>
        </Link>

        <nav className="flex flex-1 items-center gap-0.5 overflow-x-auto">
          {NAV.filter(canSee).map(({ label, href, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm transition-colors",
                isActive(href)
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon className="size-4" />
              <span className="hidden md:inline">{label}</span>
            </Link>
          ))}
        </nav>

        <ThemeToggle />
        <SignOut />
      </div>
    </header>
  );
}

// Theme toggle: the source of truth is the `data-theme` stamp the pre-paint script
// (in layout.tsx) already put on <html>, so this reads from the DOM rather than
// syncing external state into React via an effect (which the set-state-in-effect
// rule forbids). A tick counter just forces a re-render after we flip the DOM.
function ThemeToggle() {
  const [, force] = useState(0);
  const dark = typeof document !== "undefined" && document.documentElement.dataset.theme === "dark";

  function toggle() {
    const next = !dark;
    const root = document.documentElement;
    root.dataset.theme = next ? "dark" : "light";
    root.classList.toggle("dark", next); // keep Tailwind `dark:` variants in sync
    localStorage.setItem("theme", next ? "dark" : "light");
    force((n) => n + 1);
  }

  return (
    <Button variant="ghost" size="sm" onClick={toggle} aria-label="Toggle theme" className="px-2">
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}

function SignOut() {
  const router = useRouter();
  async function handle() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.refresh();
    router.push("/login");
  }
  return (
    <Button variant="outline" size="sm" onClick={handle} className="hidden sm:inline-flex">
      Sign out
    </Button>
  );
}
