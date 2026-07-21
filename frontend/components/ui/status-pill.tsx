// A status pill (step 6.2) — one component for every "state as a small coloured
// chip" the app shows: appointment status, treatment status, invoice status, the
// no-show band. Driven by a semantic TONE (good/warning/danger/neutral/accent),
// kept separate from the brand accent so status colour never impersonates a series.
//
// State is encoded in FORM as well as text: a coloured dot + wash gives the
// at-a-glance read, and the LABEL text stays in readable ink (never colour-alone,
// and never a low-contrast hue as body text). The warning yellow in particular is
// too light to read as text, so the dot carries the hue and the label stays ink.

import { cn } from "@/lib/utils";

export type Tone = "good" | "warning" | "danger" | "neutral" | "accent";

const WASH: Record<Tone, string> = {
  good: "bg-good/10 border-good/25",
  warning: "bg-warning/15 border-warning/30",
  danger: "bg-danger/10 border-danger/25",
  accent: "bg-accent border-transparent",
  neutral: "bg-muted border-transparent",
};

const DOT: Record<Tone, string> = {
  good: "bg-good",
  warning: "bg-warning",
  danger: "bg-danger",
  accent: "bg-primary",
  neutral: "bg-muted-foreground/50",
};

export function StatusPill({
  children,
  tone = "neutral",
  dot = true,
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  dot?: boolean;
  className?: string;
}) {
  const ink = tone === "accent" ? "text-accent-foreground" : "text-foreground";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        WASH[tone],
        ink,
        className,
      )}
    >
      {dot && tone !== "accent" && (
        <span className={cn("size-1.5 rounded-full", DOT[tone])} aria-hidden />
      )}
      {children}
    </span>
  );
}
