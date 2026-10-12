import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { FindingStatus, SeverityCounts } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const SEVERITIES = [
  { value: 4, key: "critical", label: "Critical" },
  { value: 3, key: "high", label: "High" },
  { value: 2, key: "medium", label: "Medium" },
  { value: 1, key: "low", label: "Low" },
  { value: 0, key: "info", label: "Info" },
] as const;

export type SeverityKey = (typeof SEVERITIES)[number]["key"];

export const severityKey = (s: number): SeverityKey => SEVERITIES.find((x) => x.value === s)?.key ?? "info";
export const severityLabel = (s: number) => SEVERITIES.find((x) => x.value === s)?.label ?? "Info";

export const STATUS_LABELS: Record<FindingStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  reopened: "Reopened",
  fixed: "Fixed",
  risk_accepted: "Risk accepted",
  false_positive: "False positive",
};

export const ACTIVE_STATUSES: FindingStatus[] = ["open", "in_progress", "reopened"];

const nf = new Intl.NumberFormat();
export const fmtNum = (n: number | null | undefined) => (n == null ? "—" : nf.format(n));

export function fmtDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31536000],
    ["month", 2592000],
    ["week", 604800],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, secs] of units) {
    if (Math.abs(diff) >= secs) return rtf.format(-Math.round(diff / secs), unit);
  }
  return "just now";
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}

export function daysSince(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
}

export const countsTotal = (c: Partial<SeverityCounts>) =>
  (c.critical ?? 0) + (c.high ?? 0) + (c.medium ?? 0) + (c.low ?? 0);

export function scanCounts(s: {
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  info_count: number;
}): SeverityCounts {
  return {
    critical: s.critical_count,
    high: s.high_count,
    medium: s.medium_count,
    low: s.low_count,
    info: s.info_count,
  };
}
