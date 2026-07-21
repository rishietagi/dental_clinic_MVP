"use client";

// The invoice screen body (5.4). Shows the frozen lines + totals, the current
// status/balance, the payments taken so far, and a form to record another
// payment. Taking payment is front-desk work (any active staff), so there's no
// role gate here — the API is the guard regardless.
//
// A "Print receipt" link goes to the sibling /receipt route (the print view).

import { useState } from "react";
import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  formatMoney,
  recordPayment,
  statusLabel,
  useInvoice,
  type Invoice,
} from "@/lib/use-invoices";
import { formatVisitDate } from "@/lib/use-visits";

const MODES = ["cash", "card", "upi"] as const;

const controlClass =
  "flex rounded-md border border-input bg-transparent px-3 py-2 text-sm " +
  "shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] " +
  "focus-visible:ring-ring/50";

function statusClass(status: string): string {
  if (status === "paid") return "text-emerald-600";
  if (status === "partially_paid") return "text-amber-600";
  return "text-muted-foreground";
}

export function InvoiceView({ invoiceId }: { invoiceId: string }) {
  const state = useInvoice(invoiceId);

  if (state.kind === "loading") {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (state.kind === "not-found") {
    return <p className="text-sm text-muted-foreground">Invoice not found.</p>;
  }
  if (state.kind === "error") {
    return <p className="text-sm text-destructive">Couldn’t load the invoice: {state.message}</p>;
  }

  return <Loaded invoice={state.invoice} refetch={state.refetch} />;
}

function Loaded({ invoice, refetch }: { invoice: Invoice; refetch: () => void }) {
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState<(typeof MODES)[number]>("cash");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const settled = invoice.status === "paid";

  async function pay(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (amount.trim() === "") {
      setError("Enter an amount.");
      return;
    }
    setBusy(true);
    const result = await recordPayment(invoice.id, { amount, mode });
    setBusy(false);
    if (result.status === "error") {
      setError(result.message);
      return;
    }
    setAmount("");
    refetch();
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Invoice</h1>
        <Link
          href={`/invoices/${invoice.id}/receipt`}
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          Print receipt
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Charges</span>
            <span className={`text-sm font-medium ${statusClass(invoice.status)}`}>
              {statusLabel(invoice.status)}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <table className="w-full text-sm">
            <tbody>
              {invoice.lines.map((line) => (
                <tr key={line.id} className="border-b last:border-0">
                  <td className="py-1.5">{line.description}</td>
                  <td className="py-1.5 text-right tabular-nums">
                    {formatMoney(line.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <dl className="flex flex-col gap-1 text-sm">
            <Row label="Subtotal" value={formatMoney(invoice.subtotal)} />
            {invoice.discount !== "0.00" && (
              <Row label="Discount" value={`− ${formatMoney(invoice.discount)}`} />
            )}
            <Row label="Total" value={formatMoney(invoice.total)} strong />
            <Row label="Paid" value={formatMoney(invoice.amount_paid)} />
            <Row label="Outstanding" value={formatMoney(invoice.outstanding)} strong />
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Payments</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {invoice.payments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No payments yet.</p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {invoice.payments.map((p) => (
                  <tr key={p.id} className="border-b last:border-0">
                    <td className="py-1.5">{formatVisitDate(p.paid_at)}</td>
                    <td className="py-1.5 capitalize text-muted-foreground">{p.mode}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatMoney(p.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {settled ? (
            <p className="text-sm text-emerald-600">This invoice is fully paid.</p>
          ) : (
            <form onSubmit={pay} className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">Amount</label>
                <Input
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  inputMode="decimal"
                  placeholder="0.00"
                  className="w-32"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">Mode</label>
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value as (typeof MODES)[number])}
                  className={`${controlClass} w-28`}
                >
                  {MODES.map((m) => (
                    <option key={m} value={m}>
                      {m.toUpperCase()}
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit" disabled={busy}>
                {busy ? "Saving…" : "Record payment"}
              </Button>
            </form>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={`tabular-nums ${strong ? "font-semibold" : ""}`}>{value}</dd>
    </div>
  );
}
