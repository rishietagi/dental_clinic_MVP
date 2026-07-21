import { GenerateInvoiceForm } from "./generate-form";

// Invoice-generate screen (step 5.4). Reached from a visit on the patient profile
// when it has no invoice yet. Shows the visit's procedures (which become the
// invoice's frozen lines), lets the biller add a discount + custom lines, then
// creates the invoice and redirects to it. `params` is a Promise in Next 16.
export default async function GenerateInvoicePage({
  params,
}: {
  params: Promise<{ visitId: string }>;
}) {
  const { visitId } = await params;

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 p-8">
      <GenerateInvoiceForm visitId={visitId} />
    </main>
  );
}
