"use client";

// Patient search + results. A search box (debounced) over GET /patients, with a
// simple Tailwind table of results. Each row's name links to the patient's
// profile at /patients/{id}.

import Link from "next/link";
import { useState } from "react";

import { EmptyState, ErrorState, SkeletonRows } from "@/components/states";
import { Input } from "@/components/ui/input";
import { StatusPill } from "@/components/ui/status-pill";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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

      {state.kind === "loading" && <SkeletonRows rows={5} />}

      {state.kind === "error" && (
        <ErrorState message={`Couldn’t load patients: ${state.message}`} />
      )}

      {state.kind === "ready" && (
        <>
          <p className="text-sm text-muted-foreground">
            {state.data.total} {state.data.total === 1 ? "patient" : "patients"}
          </p>

          {state.data.items.length === 0 ? (
            <EmptyState
              title="No patients found"
              hint={query ? "Try a different name or phone number." : "Patients you add will show up here."}
            />
          ) : (
            <div className="rounded-xl border bg-card">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Phone</TableHead>
                    <TableHead>Age</TableHead>
                    <TableHead>Gender</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {state.data.items.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell>
                        <Link
                          href={`/patients/${p.id}`}
                          className="font-medium text-primary hover:underline"
                        >
                          {p.name}
                        </Link>
                        {p.archived && (
                          <StatusPill tone="neutral" dot={false} className="ml-2">
                            archived
                          </StatusPill>
                        )}
                      </TableCell>
                      <TableCell>{p.phone ?? "—"}</TableCell>
                      <TableCell className="tabular-nums">{p.age ?? "—"}</TableCell>
                      <TableCell>{p.gender ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
