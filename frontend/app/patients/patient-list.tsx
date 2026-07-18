"use client";

// Patient search + results. A search box (debounced) over GET /patients, with a
// simple Tailwind table of results. Rows are not yet links — the profile page is
// step 2.4, so we don't fake a link to a route that doesn't exist.

import { useState } from "react";

import { Input } from "@/components/ui/input";
import { usePatientSearch } from "@/lib/use-patient-search";

export function PatientList() {
  const [query, setQuery] = useState("");
  const state = usePatientSearch(query);

  return (
    <div className="flex flex-col gap-4">
      <Input
        type="search"
        placeholder="Search by name or phone…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        aria-label="Search patients"
      />

      {state.kind === "loading" && (
        <p className="text-sm text-muted-foreground">Searching…</p>
      )}

      {state.kind === "error" && (
        <p className="text-sm text-destructive">Couldn’t load patients: {state.message}</p>
      )}

      {state.kind === "ready" && (
        <>
          <p className="text-sm text-muted-foreground">
            {state.data.total} {state.data.total === 1 ? "patient" : "patients"}
          </p>

          {state.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">No patients found.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/50 text-left text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Name</th>
                    <th className="px-3 py-2 font-medium">Phone</th>
                    <th className="px-3 py-2 font-medium">Age</th>
                    <th className="px-3 py-2 font-medium">Gender</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.items.map((p) => (
                    <tr key={p.id} className="border-b last:border-0">
                      <td className="px-3 py-2">
                        {p.name}
                        {p.archived && (
                          <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                            archived
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">{p.phone ?? "—"}</td>
                      <td className="px-3 py-2">{p.age ?? "—"}</td>
                      <td className="px-3 py-2">{p.gender ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
