"use client";

// The /calendar screen: a Day | Week toggle over the two calendar views. The day
// view (3.3) is unchanged; the week view (3.4) adds drag-drop rescheduling.

import { useState } from "react";

import { Button } from "@/components/ui/button";

import { DayView } from "./day-view";
import { WeekView } from "./week-view";

type Mode = "day" | "week";

export function CalendarView() {
  const [mode, setMode] = useState<Mode>("day");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-1" role="tablist" aria-label="Calendar view">
        <Button
          variant={mode === "day" ? "default" : "outline"}
          size="sm"
          onClick={() => setMode("day")}
          aria-pressed={mode === "day"}
        >
          Day
        </Button>
        <Button
          variant={mode === "week" ? "default" : "outline"}
          size="sm"
          onClick={() => setMode("week")}
          aria-pressed={mode === "week"}
        >
          Week
        </Button>
      </div>

      {mode === "day" ? <DayView /> : <WeekView />}
    </div>
  );
}
