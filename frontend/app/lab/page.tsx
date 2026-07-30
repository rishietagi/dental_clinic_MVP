import Link from "next/link";
import { FlaskConical } from "lucide-react";

import { LabCaseList } from "./lab-case-list";
import { buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";

// The Lab tab (6.6) — every case sent to an outside lab, what's overdue, and what's
// back waiting to be fitted. The app shell provides header/nav/main.
export default function LabPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Lab work"
        subtitle="Samples sent to the lab, and what's due back."
        action={
          <Link href="/lab/new" className={buttonVariants({ size: "sm" })}>
            <FlaskConical className="size-4" /> Send to lab
          </Link>
        }
      />
      <LabCaseList />
    </div>
  );
}
