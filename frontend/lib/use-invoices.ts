"use client";

// Invoices: reading one, resolving a visit's invoice, generating, and taking
// payments (Phase 5.2/5.3 APIs; the UI arrives in 5.4).
//
// Money crosses the wire as decimal STRINGS (the 4.1 rule — never float). This
// module never does arithmetic on amounts; it formats them with Intl.NumberFormat
// and lets the backend compute subtotal/total/balance. `formatMoney` takes the
// string as-is.

import { useCallback, useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export type InvoiceLine = {
  id: string;
  treatment_item_id: string | null;
  description: string;
  amount: string;
};

export type Payment = {
  id: string;
  amount: string;
  mode: string;
  paid_at: string;
};

export type Invoice = {
  id: string;
  patient_id: string;
  visit_id: string;
  subtotal: string;
  discount: string;
  total: string;
  status: string; // unpaid | partially_paid | paid
  created_at: string;
  updated_at: string;
  amount_paid: string;
  outstanding: string;
  lines: InvoiceLine[];
  payments: Payment[];
};

export type InvoiceLineInput = { description: string; amount: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

async function authHeaders(): Promise<Record<string, string> | null> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) return null;
  return {
    Authorization: `Bearer ${session.access_token}`,
    "Content-Type": "application/json",
  };
}

type InvoiceState =
  | { kind: "loading" }
  | { kind: "ready"; invoice: Invoice }
  | { kind: "not-found" }
  | { kind: "error"; message: string };

// One invoice by id.
export function useInvoice(invoiceId: string): InvoiceState & { refetch: () => void } {
  const [state, setState] = useState<InvoiceState>(
    apiUrl ? { kind: "loading" } : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );
  const [nonce, setNonce] = useState(0);
  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;

    (async () => {
      if (!cancelled) setState({ kind: "loading" });
      try {
        const headers = await authHeaders();
        if (!headers) throw new Error("Not signed in.");

        const res = await fetch(`${apiUrl}/invoices/${invoiceId}`, { headers });
        if (res.status === 404) {
          if (!cancelled) setState({ kind: "not-found" });
          return;
        }
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);

        const invoice = (await res.json()) as Invoice;
        if (!cancelled) setState({ kind: "ready", invoice });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load the invoice.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [invoiceId, nonce]);

  return { ...state, refetch };
}

// The invoice for a visit, or "none" if it hasn't been generated yet. The patient
// profile uses this per visit to choose "Generate invoice" vs "View invoice".
type VisitInvoiceState =
  | { kind: "loading" }
  | { kind: "none" }
  | { kind: "invoice"; invoice: Invoice }
  | { kind: "error"; message: string };

export function useVisitInvoice(visitId: string): VisitInvoiceState & { refetch: () => void } {
  const [state, setState] = useState<VisitInvoiceState>(
    apiUrl ? { kind: "loading" } : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );
  const [nonce, setNonce] = useState(0);
  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;

    (async () => {
      if (!cancelled) setState({ kind: "loading" });
      try {
        const headers = await authHeaders();
        if (!headers) throw new Error("Not signed in.");

        const res = await fetch(`${apiUrl}/visits/${visitId}/invoice`, { headers });
        if (res.status === 404) {
          // 404 here means "no invoice yet" — a normal state, not an error.
          if (!cancelled) setState({ kind: "none" });
          return;
        }
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);

        const invoice = (await res.json()) as Invoice;
        if (!cancelled) setState({ kind: "invoice", invoice });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load billing.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [visitId, nonce]);

  return { ...state, refetch };
}

// Generate an invoice from a visit. Distinguishes the outcomes the generate screen
// can hit: 409 (already invoiced) and 422 (nothing to charge / discount too big).
export type GenerateResult =
  | { status: "ok"; invoice: Invoice }
  | { status: "conflict" } // already invoiced
  | { status: "error"; message: string };

export async function generateInvoice(
  visitId: string,
  body: { discount?: string; extra_lines?: InvoiceLineInput[] },
): Promise<GenerateResult> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = await authHeaders();
    if (!headers) return { status: "error", message: "Not signed in." };

    const res = await fetch(`${apiUrl}/visits/${visitId}/invoice`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });

    if (res.ok) return { status: "ok", invoice: (await res.json()) as Invoice };
    if (res.status === 409) return { status: "conflict" };
    return { status: "error", message: await detailOr(res, "Could not create the invoice.") };
  } catch (error: unknown) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Could not create the invoice.",
    };
  }
}

export type PaymentResult =
  | { status: "ok"; invoice: Invoice }
  | { status: "error"; message: string };

export async function recordPayment(
  invoiceId: string,
  body: { amount: string; mode: string },
): Promise<PaymentResult> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = await authHeaders();
    if (!headers) return { status: "error", message: "Not signed in." };

    const res = await fetch(`${apiUrl}/invoices/${invoiceId}/payments`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });

    if (res.ok) return { status: "ok", invoice: (await res.json()) as Invoice };
    return { status: "error", message: await detailOr(res, "Could not record the payment.") };
  } catch (error: unknown) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Could not record the payment.",
    };
  }
}

// Pull FastAPI's `detail` out of an error response, else a generic message.
async function detailOr(res: Response, fallback: string): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
  } catch {
    // fall through
  }
  return `${fallback} (${res.status})`;
}

// "₹4,000.00" from a decimal string. Formats the string via Intl — never parses
// to a float and does math (the 4.1 rule). A malformed value is shown as-is.
const moneyFmt = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
});

export function formatMoney(value: string): string {
  const n = Number(value);
  if (Number.isNaN(n)) return value;
  return moneyFmt.format(n);
}

// Human labels + tone for an invoice status.
export function statusLabel(status: string): string {
  if (status === "partially_paid") return "Partially paid";
  if (status === "paid") return "Paid";
  if (status === "unpaid") return "Unpaid";
  return status;
}
