import { HealthCard } from "./health-card";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-8 p-8">
      <h1 className="text-3xl font-semibold tracking-tight">Dental Clinic</h1>
      <HealthCard />
    </main>
  );
}
