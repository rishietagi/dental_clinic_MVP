"use client";

// The OPD card, as a form section (6.10).
//
// Extracted into its own file rather than inlined: the visit form was already
// 1000 lines, and these eighteen fields are one coherent thing — the paper
// out-patient card the clinic already fills in, in its own order, so the dentist
// can transcribe top-to-bottom without hunting.
//
// Two decisions that keep it from becoming a wall of empty boxes:
//
//   1. **Quick-fill chips.** Dentists write "NAD" (no abnormality detected) and
//      "NRMH" (no relevant medical history) constantly. Typing that seven times
//      per visit is exactly why structured forms get abandoned, so each field
//      has a one-click chip and the section has a "NAD all".
//   2. **The examination collapses.** A routine scaling fills almost none of
//      this; it starts closed and opens itself if anything is already filled.
//
// Everything is optional. Values are held as strings and converted to
// null-or-trimmed at submit by `toClinicalBody`.

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { Input } from "@/components/ui/input";
import {
  INVESTIGATION_LABELS,
  type ClinicalRecord,
  type Investigation,
} from "@/lib/use-visits";

// Matches components/ui/input.tsx closely enough to look of a piece.
const controlClass =
  "flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm " +
  "shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] " +
  "focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50";

/** Every clinical field, held as a string for the form. */
export type ClinicalFields = {
  history_note: string;
  bp_systolic: string;
  bp_diastolic: string;
  habits: string;
  extra_oral: string;
  intra_oral: string;
  soft_tissues: string;
  hard_tissue: string;
  occlusion: string;
  missing_teeth: string;
  other_findings: string;
  investigations: Investigation[];
  investigation_notes: string;
  provisional_diagnosis: string;
  differential_diagnosis: string;
  final_diagnosis: string;
  referred_to: string;
  referral_note: string;
};

export const EMPTY_CLINICAL: ClinicalFields = {
  history_note: "",
  bp_systolic: "",
  bp_diastolic: "",
  habits: "",
  extra_oral: "",
  intra_oral: "",
  soft_tissues: "",
  hard_tissue: "",
  occlusion: "",
  missing_teeth: "",
  other_findings: "",
  investigations: [],
  investigation_notes: "",
  provisional_diagnosis: "",
  differential_diagnosis: "",
  final_diagnosis: "",
  referred_to: "",
  referral_note: "",
};

// The examination fields, in the card's order. Used for both rendering and the
// "NAD all" chip, so the two can't drift apart.
const EXAM_FIELDS: { key: keyof ClinicalFields; label: string; placeholder?: string }[] = [
  { key: "habits", label: "Habits", placeholder: "Tobacco, betel nut, bruxism…" },
  { key: "extra_oral", label: "Extra oral" },
  { key: "intra_oral", label: "Intra oral" },
  { key: "soft_tissues", label: "Soft tissues" },
  { key: "hard_tissue", label: "Hard tissue / caries", placeholder: "e.g. Proximal caries 26" },
  { key: "occlusion", label: "Occlusion", placeholder: "e.g. Mesial step terminal plane" },
  { key: "missing_teeth", label: "Missing teeth" },
  { key: "other_findings", label: "Others" },
];

// The referral destinations on the clinic's card.
const DEPARTMENTS = [
  "Oral Surgery",
  "Prosthodontics",
  "Periodontics",
  "Conservative Dentistry (PCD)",
  "Orthodontics",
  "Oral Pathology",
  "Pedodontics",
  "Cons. & Endo",
  "Implantology",
];

const INVESTIGATION_ORDER: Investigation[] = [
  "iopa",
  "opg_conventional",
  "opg_digital",
  "other",
];

/** Trim, and turn blanks into nulls, ready for the API. */
export function toClinicalBody(f: ClinicalFields): Partial<ClinicalRecord> {
  const text = (v: string) => (v.trim() === "" ? null : v.trim());
  // BP is the only numeric pair. Left blank it must be null, not 0 — a recorded
  // zero would be a clinical claim nobody made.
  const num = (v: string) => (v.trim() === "" ? null : Number(v));

  return {
    history_note: text(f.history_note),
    bp_systolic: num(f.bp_systolic),
    bp_diastolic: num(f.bp_diastolic),
    habits: text(f.habits),
    extra_oral: text(f.extra_oral),
    intra_oral: text(f.intra_oral),
    soft_tissues: text(f.soft_tissues),
    hard_tissue: text(f.hard_tissue),
    occlusion: text(f.occlusion),
    missing_teeth: text(f.missing_teeth),
    other_findings: text(f.other_findings),
    investigations: f.investigations,
    investigation_notes: text(f.investigation_notes),
    provisional_diagnosis: text(f.provisional_diagnosis),
    differential_diagnosis: text(f.differential_diagnosis),
    final_diagnosis: text(f.final_diagnosis),
    referred_to: text(f.referred_to),
    referral_note: text(f.referral_note),
  };
}

function Chip({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full border border-input px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-primary hover:bg-primary hover:text-primary-foreground"
    >
      {label}
    </button>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  quickFill = "NAD",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  quickFill?: string | null;
}) {
  const id = `cf-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-xs text-muted-foreground">
          {label}
        </label>
        {quickFill && value.trim() === "" && (
          <Chip label={quickFill} onClick={() => onChange(quickFill)} />
        )}
      </div>
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  );
}

export function ClinicalRecordSection({
  value,
  onChange,
}: {
  value: ClinicalFields;
  onChange: (next: ClinicalFields) => void;
}) {
  const anyExamFilled = EXAM_FIELDS.some(
    (f) => String(value[f.key] ?? "").trim() !== "",
  );
  // Open if there's already something to see; otherwise start collapsed so a
  // simple cleaning is a short form.
  const [examOpen, setExamOpen] = useState(anyExamFilled);

  function set<K extends keyof ClinicalFields>(key: K, v: ClinicalFields[K]) {
    onChange({ ...value, [key]: v });
  }

  function toggleInvestigation(inv: Investigation) {
    const next = value.investigations.includes(inv)
      ? value.investigations.filter((i) => i !== inv)
      : [...value.investigations, inv];
    set("investigations", next);
  }

  const bpHigh =
    Number(value.bp_systolic) >= 140 || Number(value.bp_diastolic) >= 90;

  return (
    <div className="flex flex-col gap-4">
      {/* --- history + vitals --- */}
      <div className="flex flex-col gap-3">
        <Field
          label="Medical / dental / drug / allergy history"
          value={value.history_note}
          onChange={(v) => set("history_note", v)}
          placeholder="Anything relevant today"
          quickFill="NRMH"
        />
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">
              Blood pressure (optional)
            </label>
            <div className="flex items-center gap-2">
              <Input
                value={value.bp_systolic}
                onChange={(e) => set("bp_systolic", e.target.value)}
                inputMode="numeric"
                placeholder="120"
                className="w-20"
                aria-label="Systolic"
              />
              <span className="text-muted-foreground">/</span>
              <Input
                value={value.bp_diastolic}
                onChange={(e) => set("bp_diastolic", e.target.value)}
                inputMode="numeric"
                placeholder="80"
                className="w-20"
                aria-label="Diastolic"
              />
              <span className="text-xs text-muted-foreground">mmHg</span>
            </div>
          </div>
          {bpHigh && (
            <p className="pb-2 text-sm text-warning">
              Raised — worth checking before an extraction or anaesthetic.
            </p>
          )}
        </div>
      </div>

      {/* --- examination (collapsible) --- */}
      <div className="rounded-lg border">
        <div className="flex items-center justify-between gap-2 px-3 py-2">
          <button
            type="button"
            onClick={() => setExamOpen((o) => !o)}
            className="flex items-center gap-1.5 text-sm font-medium"
          >
            {examOpen ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
            Examination
            {!examOpen && anyExamFilled && (
              <span className="text-xs font-normal text-muted-foreground">
                (filled)
              </span>
            )}
          </button>
          {examOpen && (
            <Chip
              label="NAD all"
              onClick={() => {
                const next = { ...value };
                for (const f of EXAM_FIELDS) {
                  if (String(next[f.key] ?? "").trim() === "") {
                    (next[f.key] as string) = "NAD";
                  }
                }
                onChange(next);
              }}
            />
          )}
        </div>

        {examOpen && (
          <div className="grid gap-3 border-t p-3 sm:grid-cols-2">
            {EXAM_FIELDS.map((f) => (
              <Field
                key={f.key}
                label={f.label}
                value={String(value[f.key] ?? "")}
                onChange={(v) => set(f.key, v as never)}
                placeholder={f.placeholder}
              />
            ))}
          </div>
        )}
      </div>

      {/* --- investigations --- */}
      <div className="flex flex-col gap-2">
        <span className="text-xs text-muted-foreground">Investigations</span>
        <div className="flex flex-wrap gap-x-5 gap-y-2">
          {INVESTIGATION_ORDER.map((inv) => (
            <label key={inv} className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={value.investigations.includes(inv)}
                onChange={() => toggleInvestigation(inv)}
              />
              {INVESTIGATION_LABELS[inv]}
            </label>
          ))}
        </div>
        {value.investigations.length > 0 && (
          <Input
            value={value.investigation_notes}
            onChange={(e) => set("investigation_notes", e.target.value)}
            placeholder="e.g. IOPA wrt 26"
          />
        )}
      </div>

      {/* --- diagnosis: the clinical conclusion, so it gets weight --- */}
      <div className="flex flex-col gap-3 rounded-lg border border-primary/30 bg-primary/5 p-3">
        <span className="text-sm font-medium">Diagnosis</span>
        <div className="flex flex-col gap-1">
          <label htmlFor="cf-prov" className="text-xs text-muted-foreground">
            Provisional diagnosis
          </label>
          <Input
            id="cf-prov"
            value={value.provisional_diagnosis}
            onChange={(e) => set("provisional_diagnosis", e.target.value)}
            placeholder="e.g. Chronic irreversible pulpitis 26"
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <label htmlFor="cf-dd" className="text-xs text-muted-foreground">
              Differential diagnosis (D/D)
            </label>
            <Input
              id="cf-dd"
              value={value.differential_diagnosis}
              onChange={(e) => set("differential_diagnosis", e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="cf-final" className="text-xs text-muted-foreground">
              Final diagnosis
            </label>
            <Input
              id="cf-final"
              value={value.final_diagnosis}
              onChange={(e) => set("final_diagnosis", e.target.value)}
              placeholder="Once investigations are back"
            />
          </div>
        </div>
      </div>

      {/* --- referral --- */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="cf-ref" className="text-xs text-muted-foreground">
            Refer to (optional)
          </label>
          <select
            id="cf-ref"
            value={value.referred_to}
            onChange={(e) => set("referred_to", e.target.value)}
            className={`${controlClass} w-64`}
          >
            <option value="">— not referred —</option>
            {DEPARTMENTS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        {value.referred_to && (
          <div className="flex flex-1 flex-col gap-1">
            <label htmlFor="cf-refnote" className="text-xs text-muted-foreground">
              Reason for referral
            </label>
            <Input
              id="cf-refnote"
              value={value.referral_note}
              onChange={(e) => set("referral_note", e.target.value)}
              placeholder="e.g. For RCT"
            />
          </div>
        )}
      </div>
    </div>
  );
}
