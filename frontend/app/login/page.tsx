import { LoginForm } from "./login-form";

// Public route: the middleware guard lets signed-out users reach /login (and
// bounces already-signed-in users back to home). Server component wrapper — the
// interactive part lives in the client LoginForm.

export default function LoginPage() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center p-8">
      <LoginForm />
    </main>
  );
}
