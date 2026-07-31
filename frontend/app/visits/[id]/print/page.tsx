import { OpdSheet } from "./opd-sheet";

// Printable OPD record (6.10). A print-styled view of one visit, laid out like
// the clinic's paper out-patient card. The Print button calls window.print() and
// the controls are .no-print, so only the record itself reaches paper (the
// @media print rule lives in globals.css — same pattern as the 5.4 receipt).
export default async function VisitPrintPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <OpdSheet visitId={id} />;
}
