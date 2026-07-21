import { Receipt } from "./receipt";

// Printable receipt (step 5.4). A print-styled view of one invoice; the Print
// button calls window.print() and the app chrome is marked .no-print so only the
// receipt itself prints (the @media print rule lives in globals.css).
export default async function ReceiptPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <Receipt invoiceId={id} />;
}
