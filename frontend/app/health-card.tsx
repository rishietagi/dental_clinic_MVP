"use client";

import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Health = { status: string; environment: string };

type State =
  | { kind: "loading" }
  | { kind: "ok"; health: Health }
  | { kind: "error"; message: string };

// This fetch runs in the browser, so NEXT_PUBLIC_API_URL must be a URL the
// browser can reach. Never a Docker service hostname like http://backend:8000 —
// a clinic PC cannot resolve that, and the failure looks like a CORS error.
const apiUrl = process.env.NEXT_PUBLIC_API_URL;

// A missing API URL is knowable at module load, so it seeds the initial state
// rather than being set from inside the effect.
const initialState: State = apiUrl
  ? { kind: "loading" }
  : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." };

export function HealthCard() {
  const [state, setState] = useState<State>(initialState);

  useEffect(() => {
    if (!apiUrl) {
      return;
    }

    let cancelled = false;

    fetch(`${apiUrl}/health`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`);
        }
        return response.json() as Promise<Health>;
      })
      .then((health) => {
        if (!cancelled) {
          setState({ kind: "ok", health });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : "Cannot reach the backend.";
          setState({ kind: "error", message });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>
          {state.kind === "loading" && "Checking system…"}
          {state.kind === "ok" && (
            <span className="text-green-600 dark:text-green-500">System OK</span>
          )}
          {state.kind === "error" && (
            <span className="text-red-600 dark:text-red-500">System unavailable</span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        {state.kind === "loading" && <p>Contacting the backend…</p>}
        {state.kind === "ok" && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <dt>Backend</dt>
            <dd>{state.health.status}</dd>
            <dt>Environment</dt>
            <dd>{state.health.environment}</dd>
          </dl>
        )}
        {state.kind === "error" && (
          <div className="space-y-1">
            <p>{state.message}</p>
            <p>Is the backend running at {apiUrl ?? "(unset)"}?</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
