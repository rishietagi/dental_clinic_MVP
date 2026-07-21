"use client";

// Practice reports (step 6.1): revenue trend, procedure mix, no-show rate.
//
// One fetch of GET /reports (dentist/admin) drives the whole screen. Money values
// are decimal strings — formatted via formatMoney (from use-invoices), never float
// math (the 4.1 rule).

import { useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export type RevenuePoint = { month: string; total: string };
export type ProcedureMixRow = { name: string; count: number; revenue: string };
export type NoShowSummary = {
  total: number;
  no_show: number;
  done: number;
  cancelled: number;
  rate: number;
};

export type Reports = {
  revenue_trend: RevenuePoint[];
  procedure_mix: ProcedureMixRow[];
  no_show: NoShowSummary;
};

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: Reports }
  | { kind: "error"; message: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

export function useReports(): State {
  const [state, setState] = useState<State>(
    apiUrl ? { kind: "loading" } : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;

    (async () => {
      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (!session) throw new Error("Not signed in.");

        const res = await fetch(`${apiUrl}/reports`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (res.status === 403) throw new Error("Reports are for the dentist/admin only.");
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);

        const data = (await res.json()) as Reports;
        if (!cancelled) setState({ kind: "ready", data });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load reports.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

// "Jul 2026" from a "YYYY-MM" month key.
export function formatMonth(monthKey: string): string {
  const [y, m] = monthKey.split("-").map(Number);
  if (!y || !m) return monthKey;
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, {
    month: "short",
    year: "numeric",
  });
}
