"use client";

// The clinic-settings form (step 4.9).
//
// Any staff sees the current values; only an admin sees the editable form — but
// that's convenience, NOT security: the API rejects a non-admin PATCH with 403
// regardless, and a 403 that slips through is surfaced inline.
//
// Hours are whole-hour selects; slot is a small number; timezone is a short IANA
// list (the clinic isn't going to need every zone — Asia/Kolkata plus a few for
// safety). The API validates the zone, so an unlisted one would 422.

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCurrentStaff } from "@/lib/use-current-staff";
import {
  updateClinicSettings,
  useClinicSettings,
  type ClinicSettings,
} from "@/lib/use-clinic-settings";
import type { MutationResult } from "@/lib/use-treatment-items";

const controlClass =
  "flex rounded-md border border-input bg-transparent px-3 py-2 text-sm " +
  "shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] " +
  "focus-visible:ring-ring/50";

// A short, practical list — the clinic is in India; the rest are here so a wrong
// browser locale isn't a trap. The API accepts any valid IANA zone.
const TIMEZONES = [
  "Asia/Kolkata",
  "UTC",
  "Asia/Dubai",
  "Europe/London",
  "America/New_York",
];

function messageFor(result: MutationResult): string | null {
  if (result === "ok") return null;
  if (result === "forbidden") return "Only an admin can change clinic settings.";
  if (result === "conflict") return "Please try again.";
  return result.error;
}

export function ClinicSettingsForm() {
  const { settings, state, refetch } = useClinicSettings();
  const staffState = useCurrentStaff();

  const isAdmin =
    staffState.kind === "staff" && staffState.staff.roles.includes("admin");

  // Local edit copy. Rather than sync it from settings in an effect (which
  // triggers cascading renders), we re-seed it *during render* when the fetched
  // values change identity — the React "adjust state while rendering" idiom.
  const settingsKey = `${settings.open_hour}-${settings.close_hour}-${settings.slot_minutes}-${settings.timezone}`;
  const [draft, setDraft] = useState<ClinicSettings>(settings);
  const [seededKey, setSeededKey] = useState(settingsKey);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  if (state === "ready" && seededKey !== settingsKey) {
    setDraft(settings);
    setSeededKey(settingsKey);
  }

  const current = draft;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(false);

    if (current.close_hour <= current.open_hour) {
      setError("Closing hour must be after opening hour.");
      return;
    }

    setBusy(true);
    const result = await updateClinicSettings({
      open_hour: current.open_hour,
      close_hour: current.close_hour,
      slot_minutes: current.slot_minutes,
      timezone: current.timezone,
    });
    setBusy(false);

    const msg = messageFor(result);
    if (msg) {
      setError(msg);
      return;
    }
    setSaved(true);
    refetch();
  }

  if (state === "error") {
    return (
      <p className="text-sm text-destructive">Couldn’t load clinic settings.</p>
    );
  }

  // Read-only view for non-admins.
  if (!isAdmin) {
    return (
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Hours</dt>
        <dd>
          {String(settings.open_hour).padStart(2, "0")}:00–
          {String(settings.close_hour).padStart(2, "0")}:00
        </dd>
        <dt className="text-muted-foreground">Slot length</dt>
        <dd>{settings.slot_minutes} min</dd>
        <dt className="text-muted-foreground">Timezone</dt>
        <dd>{settings.timezone}</dd>
        <dd className="col-span-2 mt-2 text-xs text-muted-foreground">
          Only an admin can change these.
        </dd>
      </dl>
    );
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <Field label="Opens at">
          <select
            value={current.open_hour}
            onChange={(e) =>
              setDraft({ ...current, open_hour: Number(e.target.value) })
            }
            className={`${controlClass} w-28`}
          >
            {Array.from({ length: 24 }, (_, h) => (
              <option key={h} value={h}>
                {String(h).padStart(2, "0")}:00
              </option>
            ))}
          </select>
        </Field>

        <Field label="Closes at">
          <select
            value={current.close_hour}
            onChange={(e) =>
              setDraft({ ...current, close_hour: Number(e.target.value) })
            }
            className={`${controlClass} w-28`}
          >
            {Array.from({ length: 24 }, (_, i) => i + 1).map((h) => (
              <option key={h} value={h}>
                {String(h).padStart(2, "0")}:00
              </option>
            ))}
          </select>
        </Field>

        <Field label="Slot (min)">
          <Input
            value={String(current.slot_minutes)}
            onChange={(e) =>
              setDraft({ ...current, slot_minutes: Number(e.target.value) || 0 })
            }
            inputMode="numeric"
            className="w-24"
          />
        </Field>

        <Field label="Timezone">
          <select
            value={current.timezone}
            onChange={(e) => setDraft({ ...current, timezone: e.target.value })}
            className={`${controlClass} w-48`}
          >
            {/* Include the current value even if it's not in the short list. */}
            {(TIMEZONES.includes(current.timezone)
              ? TIMEZONES
              : [current.timezone, ...TIMEZONES]
            ).map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {saved && <p className="text-sm text-emerald-600">Saved.</p>}

      <div>
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save settings"}
        </Button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}
