import { ConsultationFees } from "./consultation-fees";
import { TreatmentList } from "./treatment-list";
import { PageHeader } from "@/components/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

// Settings > Pricing (renamed from "Treatments" in 6.7).
//
// Everything the clinic charges for, in one place, under three tabs:
//   - Treatments  — dental procedures        (catalogue, kind='treatment')
//   - Medicine    — dispensed at the chair   (catalogue, kind='medicine')
//   - Consultation fee — per DENTIST, so it lives on the staff record, not the
//     catalogue. Hence a different table in the third tab.
//
// The route stays /settings/treatments so existing links keep working; only the
// label changed. Any signed-in staff can view; only an admin can edit — enforced
// by the API (require_role("admin")), the UI hiding controls as convenience.
// The app shell provides the header/nav/main.
export default function PricingSettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Pricing"
        subtitle="What the clinic charges for. Visits and invoices pick from these lists."
      />

      <Tabs defaultValue="treatments">
        <TabsList>
          <TabsTrigger value="treatments">Treatments</TabsTrigger>
          <TabsTrigger value="medicine">Medicine</TabsTrigger>
          <TabsTrigger value="consultation">Consultation fee</TabsTrigger>
        </TabsList>

        <TabsContent value="treatments">
          <TreatmentList kind="treatment" />
        </TabsContent>
        <TabsContent value="medicine">
          <TreatmentList kind="medicine" />
        </TabsContent>
        <TabsContent value="consultation">
          <ConsultationFees />
        </TabsContent>
      </Tabs>
    </div>
  );
}
