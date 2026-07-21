import { InvoiceView } from "./invoice-view";

// Invoice screen (step 5.4): lines, totals, payments, and a record-payment form.
// Reached from a visit on the patient profile after generation. The id is a PATH
// segment (an invoice id, not a patient id) — the no-PII-in-URL rule is about
// patient identifiers in query strings, which this isn't. `params` is a Promise
// in Next 16, same server-shell pattern as the patient/visit pages.
export default async function InvoicePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <div className="mx-auto w-full max-w-2xl">
      <InvoiceView invoiceId={id} />
    </div>
  );
}
