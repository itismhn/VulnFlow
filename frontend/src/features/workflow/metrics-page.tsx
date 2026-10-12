import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardHeader, PageHeader, Select, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useChartColors } from "@/lib/colors";
import { useZones } from "@/lib/queries";
import type { Metrics, MttrRow, SlaRow } from "@/lib/types";
import { cn, fmtNum } from "@/lib/utils";

const SEV_BAR: Record<string, string> = {
  critical: "bg-critical",
  high: "bg-high",
  medium: "bg-medium",
  low: "bg-low",
};

function pct(v: number | null) {
  return v == null ? "—" : `${v.toFixed(v >= 99.95 || v === 0 ? 0 : 1)}%`;
}

function complianceTone(v: number | null) {
  if (v == null) return "text-ink-3";
  return v >= 90 ? "text-ok" : v >= 70 ? "text-medium" : "text-critical";
}

/** One row: compliance bar split into met / breached, with counts. */
function SlaBar({ row, label, swatch }: { row: SlaRow; label: string; swatch?: string }) {
  const decided = row.met + row.breached;
  return (
    <div className="grid grid-cols-[110px_1fr_64px] items-center gap-3 text-sm">
      <span className="flex items-center gap-2 truncate capitalize">
        {swatch && <span className={cn("size-2 shrink-0 rounded-sm", swatch)} />}
        {label}
      </span>
      <div
        className="flex h-2.5 overflow-hidden rounded-full bg-surface-2"
        title={`${row.met} met · ${row.breached} breached`}
      >
        {decided > 0 && (
          <>
            <div className="bg-ok" style={{ width: `${(100 * row.met) / decided}%` }} />
            <div className="bg-critical/70" style={{ width: `${(100 * row.breached) / decided}%` }} />
          </>
        )}
      </div>
      <span className={cn("num text-right font-mono text-sm", complianceTone(row.compliance))}>
        {pct(row.compliance)}
      </span>
    </div>
  );
}

function MttrTable({ title, rows, capitalize }: { title: string; rows: MttrRow[]; capitalize?: boolean }) {
  const max = Math.max(1, ...rows.map((r) => r.mttr_days ?? 0));
  return (
    <Card className="overflow-hidden">
      <CardHeader title={title} description="Mean days from first detection to fix" />
      {rows.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-ink-3">No fixes in this period.</p>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((r) => (
            <li key={r.key} className="grid grid-cols-[1fr_90px_60px] items-center gap-3 px-4 py-2 text-sm">
              <span className={cn("truncate", capitalize && "capitalize")}>{r.key}</span>
              <div className="h-1.5 rounded-full bg-surface-2">
                <div
                  className="h-1.5 rounded-full bg-brand"
                  style={{ width: `${(100 * (r.mttr_days ?? 0)) / max}%` }}
                />
              </div>
              <span className="num text-right font-mono" title={`${r.fixed} fixed`}>
                {r.mttr_days == null ? "—" : `${r.mttr_days}d`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function MetricsPage() {
  const colors = useChartColors();
  const { data: zones = [] } = useZones();
  const [zone, setZone] = useState("");
  const [weeks, setWeeks] = useState(12);
  const { data, isLoading } = useQuery({
    queryKey: ["metrics", zone, weeks],
    queryFn: () => api.get<Metrics>("/metrics", { zone: zone ? [zone] : undefined, weeks }),
    placeholderData: keepPreviousData,
  });

  const velocity = (data?.velocity ?? []).map((v) => ({
    ...v,
    label: new Date(`${v.week}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
  }));
  const net = velocity.reduce((s, v) => s + v.fixed - v.opened, 0);
  const o = data?.sla_overall;

  return (
    <div className="animate-in">
      <PageHeader
        title="Remediation metrics"
        description="Are we fixing what we find, and within the agreed SLA?"
        actions={
          <>
            <Select value={zone} onChange={(e) => setZone(e.target.value)} className="w-44">
              <option value="">All zones</option>
              {zones.map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </Select>
            <Select value={weeks} onChange={(e) => setWeeks(Number(e.target.value))} className="w-40">
              <option value={4}>Last 4 weeks</option>
              <option value={12}>Last 12 weeks</option>
              <option value={26}>Last 26 weeks</option>
              <option value={52}>Last 52 weeks</option>
            </Select>
          </>
        }
      />

      {isLoading || !data || !o ? (
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-[1.2fr_1fr_1fr]">
            <Card className="px-5 py-4">
              <div className="text-xs text-ink-3">SLA compliance</div>
              <div
                className={cn("num mt-1 font-display text-4xl font-semibold", complianceTone(o.compliance))}
              >
                {pct(o.compliance)}
              </div>
              <p className="mt-1 text-xs text-ink-3">
                {fmtNum(o.met)} fixed on time of {fmtNum(o.met + o.breached)} that reached a decision (fixed,
                or past due)
              </p>
            </Card>
            <Card className="px-5 py-4">
              <div className="text-xs text-ink-3">Open and past due</div>
              <div
                className={cn(
                  "num mt-1 font-display text-4xl font-semibold",
                  o.open_overdue > 0 && "text-critical",
                )}
              >
                {fmtNum(o.open_overdue)}
              </div>
              <p className="mt-1 text-xs text-ink-3">
                {fmtNum(o.breached - o.open_overdue)} more were fixed late
              </p>
            </Card>
            <Card className="px-5 py-4">
              <div className="text-xs text-ink-3">Net backlog change</div>
              <div
                className={cn(
                  "num mt-1 font-display text-4xl font-semibold",
                  net >= 0 ? "text-ok" : "text-high",
                )}
              >
                {net > 0 ? "−" : net < 0 ? "+" : ""}
                {fmtNum(Math.abs(net))}
              </div>
              <p className="mt-1 text-xs text-ink-3">
                {net >= 0 ? "Fixing faster than finding" : "Finding faster than fixing"} over {weeks} weeks
              </p>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
            <Card>
              <CardHeader
                title="SLA by severity"
                description={
                  <span className="inline-flex items-center gap-3">
                    <span className="inline-flex items-center gap-1">
                      <span className="size-2 rounded-sm bg-ok" /> met
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <span className="size-2 rounded-sm bg-critical/70" /> breached
                    </span>
                  </span>
                }
              />
              <div className="space-y-3 px-4 py-4">
                {data.sla_by_severity.map((r) => (
                  <SlaBar key={r.key} row={r} label={r.key} swatch={SEV_BAR[r.key]} />
                ))}
                {data.sla_by_zone.length > 0 && (
                  <>
                    <div className="pt-2 text-xs font-medium text-ink-3">By zone</div>
                    {data.sla_by_zone.map((r) => (
                      <SlaBar key={r.key} row={r} label={r.key} />
                    ))}
                  </>
                )}
              </div>
            </Card>
            <Card>
              <CardHeader title="Weekly velocity" description="Findings first detected vs fixed, per week" />
              <div className="h-72 px-2 py-3">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={velocity} margin={{ left: 0, right: 12, top: 4, bottom: 0 }} barGap={2}>
                    <CartesianGrid stroke={colors.line} vertical={false} />
                    <XAxis
                      dataKey="label"
                      tick={{ fill: colors.ink3, fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      tick={{ fill: colors.ink3, fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      width={40}
                      allowDecimals={false}
                    />
                    <Tooltip
                      cursor={{ fill: colors.line, opacity: 0.4 }}
                      contentStyle={{ fontSize: 12, borderRadius: 6 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} iconType="square" iconSize={8} />
                    <Bar dataKey="opened" name="Detected" fill={colors.high} radius={[2, 2, 0, 0]} />
                    <Bar dataKey="fixed" name="Fixed" fill={colors.ok} radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <MttrTable title="Time to fix by severity" rows={data.mttr_by_severity} capitalize />
            <MttrTable title="By zone" rows={data.mttr_by_zone} />
            <MttrTable title="By owner team" rows={data.mttr_by_owner} />
          </div>
        </div>
      )}
    </div>
  );
}
