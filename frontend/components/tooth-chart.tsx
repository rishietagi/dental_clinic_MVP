"use client";

// The dental chart (6.11) — a clickable FDI tooth grid.
//
// Laid out the way a dentist reads a chart: upper arch above lower, patient's
// RIGHT on the left of the screen (as if facing them), with the deciduous teeth
// nested inside the permanent ones so a mixed-dentition child reads naturally.
//
//   18 17 16 15 14 13 12 11 │ 21 22 23 24 25 26 27 28
//         55 54 53 52 51 │ 61 62 63 64 65
//         85 84 83 82 81 │ 71 72 73 74 75
//   48 47 46 45 44 43 42 41 │ 31 32 33 34 35 36 37 38
//
// Colours come from the design system's semantic tokens (6.2) — no new palette.
// Clicking a tooth opens a condition picker; picking supersedes whatever that
// tooth said before (the server never overwrites, so the previous finding stays
// readable as history).

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  CONDITION_LABELS,
  CONDITION_ORDER,
  CONDITION_STYLES,
  markTeeth,
  type ToothCondition,
  type ToothConditionName,
} from "@/lib/use-chart";
import { cn } from "@/lib/utils";

// FDI quadrants. Upper right and lower right run 8→1 so the arch reads outward
// from the midline, matching how a chart is drawn.
const UR = ["18", "17", "16", "15", "14", "13", "12", "11"];
const UL = ["21", "22", "23", "24", "25", "26", "27", "28"];
const LR = ["48", "47", "46", "45", "44", "43", "42", "41"];
const LL = ["31", "32", "33", "34", "35", "36", "37", "38"];
// Deciduous.
const UR_D = ["55", "54", "53", "52", "51"];
const UL_D = ["61", "62", "63", "64", "65"];
const LR_D = ["85", "84", "83", "82", "81"];
const LL_D = ["71", "72", "73", "74", "75"];

function Tooth({
  tooth,
  entry,
  dimmed,
  onClick,
}: {
  tooth: string;
  entry: ToothCondition | undefined;
  dimmed: boolean;
  onClick: () => void;
}) {
  const style = entry ? CONDITION_STYLES[entry.condition] : "border-input bg-card";
  const title = entry
    ? `${tooth} — ${CONDITION_LABELS[entry.condition]}${entry.surfaces ? ` (${entry.surfaces})` : ""}`
    : `${tooth} — sound`;

  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded border text-[11px] tabular-nums transition-colors hover:ring-2 hover:ring-ring/50",
        style,
        // Deciduous teeth are de-emphasised for an adult and vice versa: both
        // sets are always present so an unexpected finding is still clickable.
        dimmed && !entry && "opacity-35",
        entry?.condition === "missing" && "line-through",
      )}
    >
      {tooth}
    </button>
  );
}

function Row({
  teeth,
  byTooth,
  dimmed,
  onPick,
}: {
  teeth: string[][];
  byTooth: Map<string, ToothCondition>;
  dimmed: boolean;
  onPick: (tooth: string) => void;
}) {
  return (
    <div className="flex items-center justify-center gap-2">
      {teeth.map((quadrant, qi) => (
        <div key={qi} className="flex gap-1">
          {quadrant.map((t) => (
            <Tooth
              key={t}
              tooth={t}
              entry={byTooth.get(t)}
              dimmed={dimmed}
              onClick={() => onPick(t)}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function ToothChart({
  patientId,
  items,
  onChanged,
  editable,
  patientAge,
  visitId,
}: {
  patientId: string;
  items: ToothCondition[];
  onChanged: () => void;
  editable: boolean;
  /** Drives which dentition is emphasised. Null = unknown, show both equally. */
  patientAge: number | null;
  /** Links findings to the sitting they were made at, when charting mid-visit. */
  visitId?: string | null;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [surfaces, setSurfaces] = useState("");
  const [busy, setBusy] = useState(false);

  const byTooth = new Map(items.map((i) => [i.tooth, i]));
  const current = open ? byTooth.get(open) : undefined;

  // Under ~13 the deciduous set is the working dentition; over ~13 it's the
  // permanent one. Never hidden, only de-emphasised — a retained baby tooth in
  // an adult is exactly the kind of thing worth charting.
  const childish = patientAge !== null && patientAge < 13;

  async function apply(condition: ToothConditionName | null) {
    if (!open) return;
    setBusy(true);
    const result = await markTeeth(
      patientId,
      [{ tooth: open, condition, surfaces: surfaces.trim() || null }],
      visitId,
    );
    setBusy(false);

    if (result.status === "ok") {
      toast.success(
        condition
          ? `${open} — ${CONDITION_LABELS[condition]}`
          : `${open} cleared`,
      );
      setOpen(null);
      setSurfaces("");
      onChanged();
      return;
    }
    toast.error(
      result.status === "forbidden"
        ? "Only a dentist can change the chart."
        : result.message,
    );
  }

  function pick(tooth: string) {
    if (!editable) return;
    setOpen(tooth);
    setSurfaces(byTooth.get(tooth)?.surfaces ?? "");
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-x-auto">
        <div className="flex min-w-fit flex-col gap-1.5 py-2">
          <Row teeth={[UR, UL]} byTooth={byTooth} dimmed={childish} onPick={pick} />
          <Row teeth={[UR_D, UL_D]} byTooth={byTooth} dimmed={!childish} onPick={pick} />
          <div className="my-1 border-t" />
          <Row teeth={[LR_D, LL_D]} byTooth={byTooth} dimmed={!childish} onPick={pick} />
          <Row teeth={[LR, LL]} byTooth={byTooth} dimmed={childish} onPick={pick} />
        </div>
      </div>

      {/* Legend — only for conditions actually present, so it stays short. */}
      {items.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {CONDITION_ORDER.filter((c) => items.some((i) => i.condition === c)).map(
            (c) => (
              <span key={c} className="flex items-center gap-1.5">
                <span className={cn("size-3 rounded border", CONDITION_STYLES[c])} />
                {CONDITION_LABELS[c]}
              </span>
            ),
          )}
        </div>
      )}

      {items.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Nothing charted yet — every tooth is recorded as sound.
          {editable && " Click a tooth to mark a finding."}
        </p>
      )}

      <Dialog open={open !== null} onOpenChange={(v) => !v && setOpen(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              Tooth {open}
              {current && (
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  currently {CONDITION_LABELS[current.condition]}
                </span>
              )}
            </DialogTitle>
          </DialogHeader>

          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">
                Surfaces (optional)
              </label>
              <Input
                value={surfaces}
                onChange={(e) => setSurfaces(e.target.value)}
                placeholder="MOD, O, B…"
                className="w-40"
              />
            </div>

            <div className="flex flex-wrap gap-2">
              {CONDITION_ORDER.map((c) => (
                <Button
                  key={c}
                  type="button"
                  size="sm"
                  variant={current?.condition === c ? "default" : "outline"}
                  disabled={busy}
                  onClick={() => apply(c)}
                >
                  {CONDITION_LABELS[c]}
                </Button>
              ))}
            </div>

            {current && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => apply(null)}
                className="self-start"
              >
                Clear — this tooth is sound
              </Button>
            )}

            <p className="text-xs text-muted-foreground">
              Previous findings are kept as history, never overwritten.
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
