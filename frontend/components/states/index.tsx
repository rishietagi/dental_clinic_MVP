// Shared state components (step 6.2) — one consistent look for the loading, error,
// and empty states that were previously ~60 ad-hoc <p> strings across the app.
//
// The copy stays specific per screen (an empty patient list says something different
// from an empty file list); these just give every state the same shape, spacing, and
// iconography so the app reads as one system.

import { AlertTriangle, Inbox, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function LoadingState({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex items-center gap-2 py-6 text-sm text-muted-foreground", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
  className,
}: {
  message: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-start gap-2 rounded-lg border border-danger/30 bg-danger/5 p-4 text-sm",
        className,
      )}
      role="alert"
    >
      <div className="flex items-center gap-2 text-danger">
        <AlertTriangle className="size-4" aria-hidden />
        <span className="font-medium">Something went wrong</span>
      </div>
      <p className="text-muted-foreground">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  icon,
  action,
  className,
}: {
  title: string;
  hint?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-2 rounded-lg border border-dashed border-border/70 px-6 py-10 text-center",
        className,
      )}
    >
      <div className="text-muted-foreground/70" aria-hidden>
        {icon ?? <Inbox className="size-6" />}
      </div>
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="max-w-sm text-sm text-muted-foreground">{hint}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

// A shimmer placeholder block. Compose a few to skeleton a list/table row.
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton h-4 w-full", className)} aria-hidden />;
}

// A few skeleton rows for list/table loading — steadier than a bare spinner on
// content that has a known shape.
export function SkeletonRows({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2 py-2", className)} aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}
