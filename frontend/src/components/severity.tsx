import { Tooltip } from "@/components/ui/overlay";
import type { FindingStatus, SeverityCounts } from "@/lib/types";
import { cn, fmtNum, SEVERITIES, STATUS_LABELS, severityKey, severityLabel } from "@/lib/utils";

const bg: Record<string, string> = {
  critical: "bg-critical",
  high: "bg-high",
  medium: "bg-medium",
  low: "bg-low",
  info: "bg-info",
};
const text: Record<string, string> = {
  critical: "text-critical",
  high: "text-high",
  medium: "text-medium",
  low: "text-low",
  info: "text-info",
};

export const severityBg = (s: number) => bg[severityKey(s)];
export const severityText = (s: number) => text[severityKey(s)];

/** Compact, colour-plus-label severity pill (never colour alone). */
export function SeverityBadge({ severity, className }: { severity: number; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 min-w-16 items-center gap-1.5 rounded px-1.5 text-[11px] font-semibold",
        "bg-surface-2",
        severityText(severity),
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", severityBg(severity))} />
      {severityLabel(severity)}
    </span>
  );
}

/**
 * The recurring "severity strip": proportional segments, used on scans,
 * hosts and networks so risk shape is comparable at a glance.
 */
export function SeverityStrip({
  counts,
  className,
  showInfo = false,
  height = "h-1.5",
}: {
  counts: Partial<SeverityCounts>;
  className?: string;
  showInfo?: boolean;
  height?: string;
}) {
  const keys = SEVERITIES.filter((s) => showInfo || s.key !== "info");
  const total = keys.reduce((sum, s) => sum + (counts[s.key] ?? 0), 0);
  const label = keys.map((s) => `${s.label}: ${counts[s.key] ?? 0}`).join(" · ");
  return (
    <Tooltip content={label}>
      <div
        className={cn("flex w-full overflow-hidden rounded-full bg-none", height, className)}
        role="img"
        aria-label={label}
      >
        {total > 0 &&
          keys.map((s) => {
            const v = counts[s.key] ?? 0;
            return v ? (
              <div key={s.key} className={bg[s.key]} style={{ width: `${(v / total) * 100}%` }} />
            ) : null;
          })}
      </div>
    </Tooltip>
  );
}

/** Four tabular counters, severity-coloured; zeros fade out. */
export function SeverityCounters({
  counts,
  className,
}: {
  counts: Partial<SeverityCounts>;
  className?: string;
}) {
  return (
    <div className={cn("num flex items-center gap-3 font-mono text-xs", className)}>
      {SEVERITIES.filter((s) => s.key !== "info").map((s) => {
        const v = counts[s.key] ?? 0;
        return (
          <span
            key={s.key}
            className={cn("w-8 text-right", v ? text[s.key] : "text-ink-3/50")}
            title={s.label}
          >
            {fmtNum(v)}
          </span>
        );
      })}
    </div>
  );
}

const statusTone: Record<FindingStatus, string> = {
  open: "bg-critical/10 text-critical",
  reopened: "bg-high/12 text-high",
  in_progress: "bg-brand-soft text-brand",
  fixed: "bg-ok/12 text-ok",
  risk_accepted: "bg-medium/15 text-medium",
  false_positive: "bg-surface-2 text-ink-3",
};

export function StatusBadge({ status }: { status: FindingStatus }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded px-1.5 text-[11px] font-medium whitespace-nowrap",
        statusTone[status],
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

/** Legend row for charts and heatmaps. */
export function SeverityLegend({ withNone = false }: { withNone?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-[11px] text-ink-3">
      {SEVERITIES.filter((s) => s.key !== "info").map((s) => (
        <span key={s.key} className="inline-flex items-center gap-1.5">
          <span className={cn("size-2 rounded-sm", bg[s.key])} />
          {s.label}
        </span>
      ))}
      {withNone && (
        <>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-sm border border-ink-3/70 bg-surface" />
            Clean
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-sm bg-none/50" />
            Not scanned
          </span>
        </>
      )}
    </div>
  );
}
