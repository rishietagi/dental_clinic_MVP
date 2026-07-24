"use client";

// Toaster (sonner). The app uses a custom data-theme stamp on <html> (not
// next-themes), so we read the theme from the DOM rather than a ThemeProvider —
// the toast colours come from our tokens via the CSS vars below.

import { Toaster as Sonner, type ToasterProps } from "sonner";
import { CircleCheckIcon, InfoIcon, OctagonXIcon, TriangleAlertIcon, Loader2Icon } from "lucide-react";

const Toaster = (props: ToasterProps) => {
  const theme =
    typeof document !== "undefined" && document.documentElement.dataset.theme === "dark"
      ? "dark"
      : "light";

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      position="bottom-right"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      {...props}
    />
  );
};

export { Toaster };
