import { InvoicesList } from "./invoices-list";
import { PageHeader } from "@/components/page-header";

// Invoices ledger (6.4) — every bill with its date, patient, and balance. The app
// shell provides header/nav/main. Any active staff can view the billing history.
export default function InvoicesPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Invoices" subtitle="Every bill, newest first." />
      <InvoicesList />
    </div>
  );
}
