"use client";

// The Reports screen body (step 6.1): revenue trend, procedure mix, no-show rate.
//
// Charts follow the dataviz rules: a single data series (slot-1 blue), one axis,
// recessive grid/axis ink, tooltips on, no legend (single series — the card title
// names it), theme-aware via useChartTheme. The no-show figure is a stat tile, not
// a chart — a bare rate reads best as a big number with its counts.

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useState } from "react";

import { Lock } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusPill } from "@/components/ui/status-pill";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { noShowColor, useChartTheme } from "@/lib/chart-theme";
import { useStaff } from "@/lib/use-staff";
import { formatMoney } from "@/lib/use-invoices";
import {
  formatMonth,
  useReports,
  type DentistRevenueRow,
  type NoShowSummary,
  type ProcedureMixRow,
  type RevenuePoint,
} from "@/lib/use-reports";

const controlClass =
  "flex rounded-md border border-input bg-transparent px-3 py-2 text-sm " +
  "shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] " +
  "focus-visible:ring-ring/50";

export function ReportsView() {
  const [dentistId, setDentistId] = useState("");
  const state = useReports(dentistId || undefined);
  const dentists = useStaff("dentist");
  const dentistOptions = dentists.kind === "ready" ? dentists.items : [];

  // Not an admin (6.12). Return before the dentist filter — offering a control that
  // filters nothing would be worse than showing nothing.
  if (state.kind === "forbidden") {
    return (
      <EmptyState
        icon={<Lock className="size-6" />}
        title="Reports are for the admin login"
        hint="Practice revenue, procedure mix and no-show rates are only visible to the clinic owner. Ask her to sign in if you need these figures."
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Dentist filter — narrows the trend/mix/no-show below to one dentist. */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">Showing:</span>
        <select
          value={dentistId}
          onChange={(e) => setDentistId(e.target.value)}
          className={`${controlClass} w-56`}
        >
          <option value="">All dentists</option>
          {dentistOptions.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </div>

      {state.kind === "loading" && <LoadingState label="Loading reports…" />}
      {state.kind === "error" && (
        <ErrorState message={`Couldn’t load reports: ${state.message}`} />
      )}
      {state.kind === "ready" && (
        <>
          <RevenueTrend data={state.data.revenue_trend} />
          <ProcedureMix data={state.data.procedure_mix} />
          <NoShow data={state.data.no_show} />
          {/* Always the full comparison, regardless of the filter above. */}
          <ByDentist rows={state.data.by_dentist} />
        </>
      )}
    </div>
  );
}

function ByDentist({ rows }: { rows: DentistRevenueRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>By dentist — last 6 months</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No attributed activity yet.</p>
        ) : (
          <div className="rounded-xl border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Dentist</TableHead>
                  <TableHead className="text-right">Revenue</TableHead>
                  <TableHead className="text-right">Visits</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.dentist_id ?? "unassigned"}>
                    <TableCell className="font-medium">
                      {r.dentist_name}
                      {r.dentist_id === null && (
                        <StatusPill tone="neutral" dot={false} className="ml-2">
                          unassigned
                        </StatusPill>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatMoney(r.revenue)}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.visits}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RevenueTrend({ data }: { data: RevenuePoint[] }) {
  const theme = useChartTheme();
  const rows = data.map((d) => ({ month: formatMonth(d.month), total: Number(d.total) }));
  const empty = rows.every((r) => r.total === 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Revenue — last 6 months</CardTitle>
      </CardHeader>
      <CardContent>
        {empty ? (
          <p className="text-sm text-muted-foreground">No payments in this period yet.</p>
        ) : (
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
                <defs>
                  <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={theme.series1} stopOpacity={0.25} />
                    <stop offset="100%" stopColor={theme.series1} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={theme.grid} vertical={false} />
                <XAxis
                  dataKey="month"
                  tick={{ fill: theme.muted, fontSize: 12 }}
                  axisLine={{ stroke: theme.axis }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: theme.muted, fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  width={70}
                  tickFormatter={(v) => formatMoney(String(v))}
                />
                <Tooltip
                  formatter={(v) => [formatMoney(String(v)), "Collected"]}
                  contentStyle={{
                    background: theme.surface,
                    border: `1px solid ${theme.axis}`,
                    borderRadius: 8,
                    color: theme.primary,
                    fontSize: 12,
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="total"
                  stroke={theme.series1}
                  strokeWidth={2}
                  fill="url(#rev)"
                  dot={{ r: 3, fill: theme.series1 }}
                  activeDot={{ r: 5 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ProcedureMix({ data }: { data: ProcedureMixRow[] }) {
  const theme = useChartTheme();
  const rows = data.map((d) => ({ name: d.name, revenue: Number(d.revenue), count: d.count }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Procedure mix — last 6 months (by revenue)</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No billed procedures in this period yet.</p>
        ) : (
          <div style={{ height: Math.max(160, rows.length * 40) }} className="w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={rows}
                layout="vertical"
                margin={{ top: 4, right: 24, bottom: 4, left: 8 }}
              >
                <CartesianGrid stroke={theme.grid} horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fill: theme.muted, fontSize: 12 }}
                  axisLine={{ stroke: theme.axis }}
                  tickLine={false}
                  tickFormatter={(v) => formatMoney(String(v))}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fill: theme.secondary, fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  width={120}
                />
                <Tooltip
                  formatter={(v, _n, p) => [
                    `${formatMoney(String(v))} · ${p?.payload?.count ?? 0}×`,
                    "Revenue",
                  ]}
                  contentStyle={{
                    background: theme.surface,
                    border: `1px solid ${theme.axis}`,
                    borderRadius: 8,
                    color: theme.primary,
                    fontSize: 12,
                  }}
                />
                <Bar dataKey="revenue" fill={theme.series1} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function NoShow({ data }: { data: NoShowSummary }) {
  const theme = useChartTheme();
  const color = noShowColor(theme, data.rate);

  return (
    <Card>
      <CardHeader>
        <CardTitle>No-show rate — last 30 days</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
          <span className="text-4xl font-semibold" style={{ color }}>
            {data.rate}%
          </span>
          <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
            <Stat label="No-shows" value={data.no_show} />
            <Stat label="Attended" value={data.done} />
            <Stat label="Cancelled" value={data.cancelled} />
            <Stat label="Total booked" value={data.total} />
          </dl>
        </div>
        {data.total === 0 && (
          <p className="mt-2 text-sm text-muted-foreground">
            No appointments in the last 30 days.
          </p>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          Share of scheduled appointments (excluding cancellations) the patient didn’t attend.
        </p>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2">
      <dt>{label}</dt>
      <dd className="font-medium text-foreground tabular-nums">{value}</dd>
    </div>
  );
}
