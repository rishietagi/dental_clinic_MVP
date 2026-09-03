"use client";

// Practice reports (step 6.1): revenue trend, procedure mix, no-show rate.
//
// One fetch of GET /reports (**admin only** as of 6.12) drives the whole screen.
// Money values are decimal strings — formatted via formatMoney (from use-invoices),
// never float math (the 4.1 rule).
//
// A 403 gets its own state rather than folding into `error`: a receptionist or
// dentist landing here is not a fault, it is the guard working, and it should read
// as a calm "not for this login" rather than a red something-went-wrong panel.

import { useEffect, useState } from "react";

export type RevenuePoint = { month: string; total: string };
export type ProcedureMixRow = { name: string; count: number; revenue: string };
export type NoShowSummary = {
  total: number;
  no_show: number;
  done: number;
  cancelled: number;
  rate: number;
};

export type DentistRevenueRow = {
  dentist_id: string | null;
  dentist_name: string;
  revenue: string;
  visits: number;
};

export type Reports = {
  revenue_trend: RevenuePoint[];
  procedure_mix: ProcedureMixRow[];
  no_show: NoShowSummary;
  by_dentist: DentistRevenueRow[];
};

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: Reports }
  | { kind: "forbidden" } // signed in, but not an admin (6.12)
  | { kind: "error"; message: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

// `dentistId` narrows the trend/mix/no-show reports to one dentist; the by_dentist
// breakdown is always the full comparison.
export function useReports(dentistId?: string): State {
  const [state, setState] = useState<State>(
    apiUrl ? { kind: "loading" } : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;

    (async () => {
      if (!cancelled) setState({ kind: "loading" });
      try {
        const url = new URL(`${apiUrl}/reports`);
        if (dentistId) url.searchParams.set("dentist_id", dentistId);

        const res = await fetch(url);
        if (res.status === 403) {
          if (!cancelled) setState({ kind: "forbidden" });
          return;
        }
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
  }, [dentistId]);

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
