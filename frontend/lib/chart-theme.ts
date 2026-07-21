"use client";

// Chart theme tokens (step 6.1) — the validated dataviz palette, resolved for the
// current light/dark mode. Values come straight from the dataviz reference palette
// (validated with scripts/validate_palette.js); the single data series is slot-1
// blue, chrome/ink are the reference chrome tokens, and the no-show status colors
// are the fixed status palette.
//
// Recharts takes concrete color strings (not CSS vars) for many props, so we read
// the resolved values off the current mode. The app toggles dark via a `.dark`
// class on <html> (Tailwind) and also respects the OS setting — useChartTheme
// tracks both and returns the right set.

import { useEffect, useState } from "react";

export type ChartTheme = {
  series1: string;
  surface: string;
  primary: string;
  secondary: string;
  muted: string; // axis/labels
  grid: string;
  axis: string;
  good: string;
  warning: string;
  critical: string;
};

const LIGHT: ChartTheme = {
  series1: "#2a78d6",
  surface: "#fcfcfb",
  primary: "#0b0b0b",
  secondary: "#52514e",
  muted: "#898781",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  good: "#0ca30c",
  warning: "#fab219",
  critical: "#d03b3b",
};

const DARK: ChartTheme = {
  series1: "#3987e5",
  surface: "#1a1a19",
  primary: "#ffffff",
  secondary: "#c3c2b7",
  muted: "#898781",
  grid: "#2c2c2a",
  axis: "#383835",
  good: "#0ca30c",
  warning: "#fab219",
  critical: "#d03b3b",
};

function isDark(): boolean {
  if (typeof document === "undefined") return false;
  const root = document.documentElement;
  if (root.classList.contains("dark")) return true;
  if (root.dataset.theme === "light") return false;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function useChartTheme(): ChartTheme {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const update = () => setDark(isDark());
    update();

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", update);
    // The app toggles a `.dark` class; observe it so charts recolor on toggle.
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    });

    return () => {
      mq.removeEventListener("change", update);
      observer.disconnect();
    };
  }, []);

  return dark ? DARK : LIGHT;
}

// The status color for a no-show rate: low is good, mid warns, high is serious.
export function noShowColor(theme: ChartTheme, ratePct: number): string {
  if (ratePct >= 15) return theme.critical;
  if (ratePct >= 7) return theme.warning;
  return theme.good;
}
