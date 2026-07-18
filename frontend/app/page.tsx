import { HealthCard } from "./health-card";
import { RoleNav } from "./role-nav";
import { SignOutButton } from "./sign-out-button";
import { createClient } from "@/lib/supabase/server";

// Protected home page. The middleware guard guarantees only signed-in users get
// here, so reading the user is safe; we show their email to make the login
// visibly real. Async server component — it reads the session on the server.
export default async function Home() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-8 p-8">
      <div className="flex w-full max-w-sm items-center justify-between gap-4">
        <span className="text-sm text-muted-foreground">{user?.email}</span>
        <SignOutButton />
      </div>
      <h1 className="text-3xl font-semibold tracking-tight">Dental Clinic</h1>
      <RoleNav />
      <HealthCard />
    </main>
  );
}
