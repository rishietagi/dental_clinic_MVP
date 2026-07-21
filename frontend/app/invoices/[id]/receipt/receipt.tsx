"use client";

// The receipt itself (5.4). Clinic header from clinic_settings, the invoice's
// frozen lines + totals, the payments, and the balance. `window.print()` prints
// it; the Print/Back controls are .no-print so they don't appear on paper.
//
// The patient name needs a fetch (the invoice carries patient_id, not the name) —
// usePatient by id. Everything else is on the invoice.

import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import { useClinicSettings } from "@/lib/use-clinic-settings";
import { formatMoney, statusLabel, useInvoice, type Invoice } from "@/lib/use-invoices";
import { usePatient } from "@/lib/use-patient";
import { formatVisitDate } from "@/lib/use-visits";

export function Receipt({ invoiceId }: { invoiceId: string }) {
  const state = useInvoice(invoiceId);

  if (state.kind === "loading") {
    return <main className="mx-auto max-w-lg p-8 text-sm text-muted-foreground">Loading…</main>;
  }
  if (state.kind === "not-found") {
    return <main className="mx-auto max-w-lg p-8 text-sm text-muted-foreground">Invoice not found.</main>;
  }
  if (state.kind === "error") {
    return <main className="mx-auto max-w-lg p-8 text-sm text-destructive">{state.message}</main>;
  }

  return <Loaded invoice={state.invoice} />;
}

function Loaded({ invoice }: { invoice: Invoice }) {
  const { settings } = useClinicSettings();
  const patient = usePatient(invoice.patient_id);
  const patientName = patient.kind === "ready" ? patient.patient.name : "";

  return (
    <main className="mx-auto flex w-full max-w-lg flex-col gap-6 p-8">
      <div className="flex items-center justify-between no-print">
        <Link
          href={`/invoices/${invoice.id}`}
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          Back
        </Link>
        <Button size="sm" onClick={() => window.print()}>
          Print
        </Button>
      </div>

      {/* The printable slip. */}
      <div className="flex flex-col gap-5 rounded-lg border p-6 text-sm">
        <header className="flex flex-col items-center gap-0.5 text-center">
          <h1 className="text-lg font-semibold">{settings.clinic_name}</h1>
          {settings.address && <p className="text-muted-foreground">{settings.address}</p>}
          {settings.phone && <p className="text-muted-foreground">{settings.phone}</p>}
        </header>

        <div className="flex justify-between text-xs text-muted-foreground">
          <span>Receipt #{invoice.id.slice(0, 8)}</span>
          <span>{formatVisitDate(invoice.created_at)}</span>
        </div>

        {patientName && (
          <div>
            <span className="text-muted-foreground">Patient: </span>
            <span className="font-medium">{patientName}</span>
          </div>
        )}

        <table className="w-full">
          <tbody>
            {invoice.lines.map((line) => (
              <tr key={line.id} className="border-b last:border-0">
                <td className="py-1.5">{line.description}</td>
                <td className="py-1.5 text-right tabular-nums">{formatMoney(line.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="flex flex-col gap-1">
          <Row label="Subtotal" value={formatMoney(invoice.subtotal)} />
          {invoice.discount !== "0.00" && (
            <Row label="Discount" value={`− ${formatMoney(invoice.discount)}`} />
          )}
          <Row label="Total" value={formatMoney(invoice.total)} strong />
          <Row label="Paid" value={formatMoney(invoice.amount_paid)} />
          <Row label="Outstanding" value={formatMoney(invoice.outstanding)} strong />
        </dl>

        {invoice.payments.length > 0 && (
          <div className="flex flex-col gap-1">
            <p className="text-xs font-medium text-muted-foreground">Payments</p>
            <table className="w-full text-xs">
              <tbody>
                {invoice.payments.map((p) => (
                  <tr key={p.id}>
                    <td className="py-0.5">{formatVisitDate(p.paid_at)}</td>
                    <td className="py-0.5 capitalize text-muted-foreground">{p.mode}</td>
                    <td className="py-0.5 text-right tabular-nums">{formatMoney(p.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="text-center text-xs text-muted-foreground">
          Status: {statusLabel(invoice.status)}
        </p>
      </div>
    </main>
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
