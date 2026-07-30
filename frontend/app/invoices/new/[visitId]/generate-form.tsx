"use client";

// The invoice-generate form (5.4). The visit's recorded procedures become the
// invoice's frozen lines, priced server-side from the catalogue at generation
// time (the 5.2 snapshot rule) — so this screen lists the procedure NAMES that
// will be billed rather than guessing their prices here. The biller adds a
// discount and any custom lines, then creates the invoice.
//
// After creation the invoice is fixed (no edit endpoint in Phase 5), which is why
// the discount + custom lines are set here, before the POST.
//
// **Consultation fees (6.7)** arrive as `?consult=<amount>|<dentist name>`
// repeated, set by the visit form's "Save & draft invoice". The fee is
// per-dentist rather than a catalogue item, so it has no procedure row to be
// read back from — the query string is how it gets here. They're pre-filled as
// ordinary custom lines, so the biller can still edit or remove them.

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  generateInvoice,
  type InvoiceLineInput,
} from "@/lib/use-invoices";
import { useVisit } from "@/lib/use-visits";

// Turn the `?consult=amount|name` params into pre-filled custom lines.
// Malformed entries are skipped rather than shown as broken rows.
function consultationLines(params: URLSearchParams): InvoiceLineInput[] {
  return params
    .getAll("consult")
    .map((raw) => {
      const sep = raw.indexOf("|");
      if (sep === -1) return null;
      const amount = raw.slice(0, sep).trim();
      const name = raw.slice(sep + 1).trim();
      if (!amount || !name) return null;
      return { description: `Consultation — ${name}`, amount };
    })
    .filter((line): line is InvoiceLineInput => line !== null);
}

export function GenerateInvoiceForm({ visitId }: { visitId: string }) {
  const state = useVisit(visitId);
  const router = useRouter();
  const params = useSearchParams();

  const [discount, setDiscount] = useState("");
  // Seeded once from the URL: any consultation fees chosen on the visit screen
  // start as editable custom lines.
  const [extra, setExtra] = useState<InvoiceLineInput[]>(() =>
    consultationLines(params),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);

  if (state.kind === "loading") {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (state.kind === "not-found") {
    return <p className="text-sm text-muted-foreground">Visit not found.</p>;
  }
  if (state.kind === "error") {
    return <p className="text-sm text-destructive">Couldn’t load the visit: {state.message}</p>;
  }

  const visit = state.visit;

  function setExtraAt(i: number, patch: Partial<InvoiceLineInput>) {
    setExtra((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setConflict(false);

    // Drop blank custom lines; a half-filled one is a mistake worth flagging.
    const lines = extra.filter((r) => r.description.trim() !== "" || r.amount.trim() !== "");
    for (const r of lines) {
      if (r.description.trim() === "" || r.amount.trim() === "") {
        setError("Each custom line needs both a description and an amount.");
        return;
      }
    }

    setBusy(true);
    const result = await generateInvoice(visitId, {
      discount: discount.trim() === "" ? undefined : discount,
      extra_lines: lines.length > 0 ? lines : undefined,
    });
    setBusy(false);

    if (result.status === "ok") {
      router.push(`/invoices/${result.invoice.id}`);
      return;
    }
    if (result.status === "conflict") {
      setConflict(true);
      return;
    }
    setError(result.message);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Generate invoice</h1>
        <Link
          href={`/patients/${visit.patient_id}`}
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          Back to patient
        </Link>
      </div>

      {conflict && (
        <p className="text-sm text-amber-600">
          This visit already has an invoice.{" "}
          <Link href={`/patients/${visit.patient_id}`} className="underline">
            {/* The profile resolves the visit’s invoice and links to it. */}
            Back to the patient
          </Link>{" "}
          to view it.
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>
            {visit.treatment.title}
            {visit.treatment.tooth_ref ? ` — tooth ${visit.treatment.tooth_ref}` : ""}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="text-xs text-muted-foreground">
            These recorded procedures will be billed at their current catalogue price:
          </p>
          {visit.procedures.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No procedures recorded on this visit — add a custom line below to bill anything.
            </p>
          ) : (
            <ul className="list-disc pl-5 text-sm">
              {visit.procedures.map((p) => (
                <li key={p.id}>
                  {p.treatment_item_name}
                  {p.tooth_ref ? ` (tooth ${p.tooth_ref})` : ""}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <form onSubmit={create} className="flex flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Custom lines (optional)</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {extra.map((row, i) => (
              <div key={i} className="flex flex-wrap items-end gap-3">
                <div className="flex flex-1 flex-col gap-1">
                  <label className="text-xs text-muted-foreground">Description</label>
                  <Input
                    value={row.description}
                    onChange={(e) => setExtraAt(i, { description: e.target.value })}
                    placeholder="e.g. X-ray"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground">Amount</label>
                  <Input
                    value={row.amount}
                    onChange={(e) => setExtraAt(i, { amount: e.target.value })}
                    inputMode="decimal"
                    placeholder="0.00"
                    className="w-32"
                  />
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setExtra((rows) => rows.filter((_, j) => j !== i))}
                >
                  Remove
                </Button>
              </div>
            ))}
            <div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setExtra((rows) => [...rows, { description: "", amount: "" }])}
              >
                Add a line
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Discount</label>
            <Input
              value={discount}
              onChange={(e) => setDiscount(e.target.value)}
              inputMode="decimal"
              placeholder="0.00"
              className="w-32"
            />
          </div>
          <Button type="submit" disabled={busy}>
            {busy ? "Creating…" : "Create invoice"}
          </Button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </form>
    </div>
  );
}
