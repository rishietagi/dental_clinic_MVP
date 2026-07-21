import { CalendarView } from "./calendar-view";
import { PageHeader } from "@/components/page-header";

// Calendar route. Protected by proxy.ts and by the API (active-staff on the data
// call). The app shell provides the header/nav/main.
export default function CalendarPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Calendar" subtitle="Day and week views. Drag to reschedule." />
      <CalendarView />
    </div>
  );
}
