import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Flame, Timer, TrendingDown, TrendingUp, Upload } from "lucide-react";
import { useState } from "react";
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
import { SeverityBadge, SeverityLegend, SeverityStrip } from "@/components/severity";
import { Card, CardHeader, EmptyState, PageHeader, Select, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useChartColors } from "@/lib/colors";
import type { Dashboard, NetworkStats } from "@/lib/types";
import { cn, fmtNum, fmtRelative, STATUS_LABELS } from "@/lib/utils";

const SEV_TILES = [
  { key: "critical", label: "Critical", sev: 4, cls: "text-critical", bar: "bg-critical" },
  { key: "high", label: "High", sev: 3, cls: "text-high", bar: "bg-high" },
  { key: "medium", label: "Medium", sev: 2, cls: "text-medium", bar: "bg-medium" },
  { key: "low", label: "Low", sev: 1, cls: "text-low", bar: "bg-low" },
] as const;

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="num flex items-center gap-2">
          <span className="size-2 rounded-sm" style={{ background: p.color }} />
          <span className="capitalize text-ink-2">{p.name}</span>
          <span className="ml-auto pl-4 font-mono">{fmtNum(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

export function DashboardPage() {
  const colors = useChartColors();
  const [zone, setZone] = useState("");
  const { data: zones = [] } = useQuery({
    queryKey: ["networks", "zones"],
    queryFn: () => api.get<string[]>("/networks/zones"),
  });
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard", zone],
    queryFn: () => api.get<Dashboard>("/dashboard", { zone: zone ? [zone] : undefined }),
  });
  const { data: networks = [] } = useQuery({
    queryKey: ["networks"],
    queryFn: () => api.get<NetworkStats[]>("/networks"),
  });

  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-32" />
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-72 lg:col-span-2" />
          <Skeleton className="h-72" />
        </div>
      </div>
    );
  }

  const k = data.kpis;
  const totalOpen = k.open.critical + k.open.high + k.open.medium + k.open.low;

  if (k.scans === 0) {
    return (
      <Card>
        <EmptyState
          icon={<Upload className="size-8" />}
          title="Import your first scan"
          action={
            <p className="text-xs text-ink-3">
              Use “Import scan” in the top bar, or run the demo seed from the README.
            </p>
          }
        >
          Upload a .nessus export to see your exposure by severity, network range, and asset. Each new scan
          updates finding status automatically: new, fixed, or reopened.
        </EmptyState>
      </Card>
    );
  }

  const zoneQuery = zone ? { zone: [zone] } : {};
  // Start the chart at the first week with data, not at the edge of the window
  const firstData = data.trend.findIndex((p) => p.critical + p.high + p.medium + p.low > 0);
  const trend = data.trend.slice(Math.max(0, firstData - 1)).map((p) => ({
    ...p,
    label: new Date(p.date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
  }));

  return (
    <div className="animate-in">
      <PageHeader
        title="Exposure overview"
        description={
          <>
            {fmtNum(k.assets)} assets · last scan {fmtRelative(k.last_scan_at)} · {fmtNum(k.scans)} scans
            imported
          </>
        }
        actions={
          <Select
            value={zone}
            onChange={(e) => setZone(e.target.value)}
            className="w-52"
            aria-label="Filter by zone"
          >
            <option value="">All network zones</option>
            {zones.map((z) => (
              <option key={z}>{z}</option>
            ))}
          </Select>
        }
      />

      {/* Severity ledger: the four numbers that matter, proportionally underlined */}
      <Card className="mb-4 overflow-hidden">
        <div className="grid grid-cols-2 divide-line md:grid-cols-4 md:divide-x">
          {SEV_TILES.map((t) => {
            const v = k.open[t.key];
            return (
              <Link
                key={t.key}
                to="/findings"
                search={{ severity: [t.sev], ...zoneQuery }}
                className="group relative px-5 py-4 transition hover:bg-surface-2"
              >
                <div className="flex items-center justify-between text-xs font-medium text-ink-2">
                  {t.label}
                  <ArrowRight className="size-3.5 opacity-0 transition group-hover:opacity-100" />
                </div>
                <div
                  className={cn(
                    "num mt-1 font-display text-4xl font-semibold tracking-tight",
                    v ? t.cls : "text-ink-3",
                  )}
                >
                  {fmtNum(v)}
                </div>
                <div className="mt-0.5 text-xs text-ink-3">
                  MTTR {k.mttr_days[t.key] != null ? `${k.mttr_days[t.key]} days` : "—"}
                </div>
                <div className="absolute inset-x-0 bottom-0 h-1 bg-none">
                  <div
                    className={cn("h-full", t.bar)}
                    style={{ width: `${totalOpen ? (v / totalOpen) * 100 : 0}%` }}
                  />
                </div>
              </Link>
            );
          })}
        </div>
        <div className="grid grid-cols-2 gap-px border-t border-line bg-line md:grid-cols-4">
          <MiniStat
            icon={<Flame className="size-4 text-critical" />}
            label="Exploit available"
            value={k.exploitable}
            to={{ exploitable: true, ...zoneQuery }}
          />
          <MiniStat
            icon={<Timer className="size-4 text-high" />}
            label="Past due date"
            value={k.overdue}
            to={{ overdue: true, ...zoneQuery }}
          />
          <MiniStat
            icon={<TrendingUp className="size-4 text-ink-3" />}
            label="New in 30 days"
            value={k.new_30d}
          />
          <MiniStat
            icon={<TrendingDown className="size-4 text-ok" />}
            label="Fixed in 30 days"
            value={k.fixed_30d}
          />
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Open findings over time"
            description="Weekly, reconstructed from first-seen and fixed dates"
            actions={<SeverityLegend />}
          />
          <div className="h-64 px-2 pt-4 pb-2">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend} margin={{ left: 0, right: 12, top: 4, bottom: 0 }}>
                <CartesianGrid stroke={colors.line} vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 11, fill: colors.ink3 }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={24}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: colors.ink3 }}
                  tickLine={false}
                  axisLine={false}
                  width={40}
                  allowDecimals={false}
                />
                <Tooltip content={<ChartTooltip />} />
                {(["low", "medium", "high", "critical"] as const).map((s) => (
                  <Area
                    key={s}
                    type="monotone"
                    dataKey={s}
                    stackId="1"
                    stroke={colors[s]}
                    fill={colors[s]}
                    fillOpacity={0.75}
                    strokeWidth={1.5}
                    isAnimationActive={false}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardHeader title="Finding status" description="All findings in scope, including closed" />
          <ul className="space-y-2.5 px-4 py-4">
            {(Object.keys(STATUS_LABELS) as (keyof typeof STATUS_LABELS)[]).map((s) => {
              const total = Object.values(data.status).reduce((a, b) => a + b, 0) || 1;
              const v = data.status[s] ?? 0;
              return (
                <li key={s}>
                  <Link to="/findings" search={{ status: [s], ...zoneQuery }} className="group block">
                    <div className="flex justify-between text-sm">
                      <span className="text-ink-2 group-hover:text-ink">{STATUS_LABELS[s]}</span>
                      <span className="num font-mono text-xs">{fmtNum(v)}</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-surface-2">
                      <div
                        className="h-full rounded-full bg-ink-3/60"
                        style={{ width: `${(v / total) * 100}%` }}
                      />
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Top vulnerabilities"
            description="Ranked by severity, then by number of affected hosts"
            actions={
              <Link to="/vulnerabilities" className="text-xs text-brand hover:underline">
                All vulnerabilities
              </Link>
            }
          />
          <ul className="divide-y divide-line">
            {data.top_vulns.map((v) => (
              <li key={v.plugin_id}>
                <Link
                  to="/vulnerabilities/$pluginId"
                  params={{ pluginId: String(v.plugin_id) }}
                  className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-2"
                >
                  <SeverityBadge severity={v.severity} />
                  <span className="min-w-0 flex-1 truncate text-sm">{v.name}</span>
                  {v.exploit_available && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-critical">
                      <Flame className="size-3" /> Exploit
                    </span>
                  )}
                  <span className="num w-20 text-right font-mono text-xs text-ink-2">
                    {fmtNum(v.hosts)} hosts
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <CardHeader
            title="Most at-risk assets"
            description="Severity-weighted, scaled by criticality"
            actions={
              <Link to="/assets" className="text-xs text-brand hover:underline">
                All assets
              </Link>
            }
          />
          <ul className="divide-y divide-line">
            {data.top_hosts.map((h) => (
              <li key={h.asset_id}>
                <Link
                  to="/assets/$assetId"
                  params={{ assetId: String(h.asset_id) }}
                  className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-2"
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-mono text-sm">{h.ip}</div>
                    <div className="truncate text-xs text-ink-3">{h.hostname || "—"}</div>
                  </div>
                  <div className="text-right">
                    <div className="num font-mono text-sm font-medium">{h.risk_score}</div>
                    <div className="text-[11px] text-ink-3">
                      <span className="text-critical">{h.critical}C</span> ·{" "}
                      <span className="text-high">{h.high}H</span>
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="Exposure by network zone" description="Open findings per zone" />
          <div className="px-2 pt-3 pb-2" style={{ height: Math.max(160, data.by_zone.length * 38 + 30) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.by_zone} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid stroke={colors.line} horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fontSize: 11, fill: colors.ink3 }}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={120}
                  tick={{ fontSize: 12, fill: colors.ink3 }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: colors.line, opacity: 0.4 }} />
                {(["critical", "high", "medium", "low"] as const).map((s, i, arr) => (
                  <Bar
                    key={s}
                    dataKey={s}
                    stackId="z"
                    fill={colors[s]}
                    barSize={18}
                    radius={i === arr.length - 1 ? [0, 3, 3, 0] : 0}
                    isAnimationActive={false}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardHeader title="Age of open findings" description="Time since first detection" />
          <ul className="space-y-3 px-4 py-4">
            {data.age.map((a) => {
              const total = a.critical + a.high + a.medium + a.low;
              return (
                <li key={a.label}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-ink-2">{a.label}</span>
                    <span className="num font-mono text-xs">{fmtNum(total)}</span>
                  </div>
                  <SeverityStrip counts={a} height="h-2" />
                </li>
              );
            })}
          </ul>
        </Card>

        {networks.length > 0 && (
          <Card className="lg:col-span-3">
            <CardHeader
              title="Networks"
              description="Open findings per IP range"
              actions={
                <Link to="/networks" className="text-xs text-brand hover:underline">
                  Manage networks
                </Link>
              }
            />
            <div className="grid sm:grid-cols-2 xl:grid-cols-4 [&>*]:border-r [&>*]:border-b [&>*]:border-line">
              {networks.slice(0, 8).map((n) => (
                <Link
                  key={n.id}
                  to="/findings"
                  search={{ network_id: [n.id] }}
                  className="bg-surface px-4 py-3 hover:bg-surface-2"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-sm font-medium">{n.name}</span>
                    <span className="font-mono text-[11px] text-ink-3">{n.cidr}</span>
                  </div>
                  <SeverityStrip counts={n.open} className="my-2" />
                  <div className="num flex gap-3 font-mono text-[11px] text-ink-3">
                    <span className="text-critical">{n.open.critical} C</span>
                    <span className="text-high">{n.open.high} H</span>
                    <span>{n.asset_count} assets</span>
                  </div>
                </Link>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

function MiniStat({
  icon,
  label,
  value,
  to,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  to?: Record<string, unknown>;
}) {
  const body = (
    <div className="flex items-center gap-3 bg-surface px-5 py-3 transition hover:bg-surface-2">
      {icon}
      <span className="text-xs text-ink-2">{label}</span>
      <span className="num ml-auto font-mono text-sm font-medium">{fmtNum(value)}</span>
    </div>
  );
  return to ? (
    <Link to="/findings" search={to}>
      {body}
    </Link>
  ) : (
    body
  );
}
