"use client";

// The dashboard's date line (fixed in 10.7).
//
// THE BUG THIS EXISTS TO FIX
//   `app/page.tsx` is a SERVER component, so its `new Date()` ran on the Node
//   server when the page was rendered — and Next.js then cached that render. In
//   the packaged desktop app the server starts once and the page is served from
//   that cache, so the heading FROZE on whatever date the app first rendered,
//   while every list below it (which fetches in the browser) showed today.
//   The clinic saw "Thursday, 3 September" above a correct list of today's
//   appointments.
//
//   Rendering it in the browser fixes that: the client evaluates the date on
//   every load, from the machine's own clock.
//
// It also formats in the CLINIC timezone, like the rest of the app (the 4.9
// rule — `todayIso`, the worklists, the day view all do this). Using the
// browser's local zone would put the heading a day out from the lists it sits
// above whenever the two disagree.
//
// The ticker matters for the one case a clinic actually hits: the app is left
// open overnight. Without it, a machine opened on Monday still says Monday on
// Tuesday morning.

import { useEffect, useState } from "react";
import { formatInTimeZone } from "date-fns-tz";

import { useClinicSettings } from "@/lib/use-clinic-settings";

function label(tz: string): string {
  // e.g. "Thursday, 3 September 2026"
  return formatInTimeZone(new Date(), tz, "EEEE, d MMMM yyyy");
}

export function DashboardDate() {
  const { settings } = useClinicSettings();
  const tz = settings.timezone;

  // A tick counter, not a copy of the date: the label is DERIVED on every
  // render rather than stored in state and synced from an effect (this repo's
  // set-state-in-effect rule, same reasoning as the 6.2 theme toggle). The
  // interval only nudges React to re-render.
  const [, tick] = useState(0);

  useEffect(() => {
    // Re-render each minute so an app left open overnight rolls over to the new
    // day instead of still showing yesterday.
    const id = setInterval(() => tick((n) => n + 1), 60_000);
    return () => clearInterval(id);
  }, []);

  return <>{label(tz)}</>;
}
