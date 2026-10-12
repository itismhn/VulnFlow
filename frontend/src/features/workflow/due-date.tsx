import { cn, fmtDate } from "@/lib/utils";

function daysUntil(iso: string): number {
  const due = new Date(`${iso}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((due.getTime() - today.getTime()) / 86_400_000);
}

/** Due date with an overdue / due-soon state. Only meaningful for active findings. */
export function DueDate({
  date,
  source,
  active = true,
  className,
}: {
  date: string | null;
  source?: "sla" | "manual" | null;
  active?: boolean;
  className?: string;
}) {
  if (!date) return null;
  const left = daysUntil(date);
  const overdue = active && left < 0;
  const soon = active && left >= 0 && left <= 7;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[11px] whitespace-nowrap",
        overdue ? "font-medium text-critical" : soon ? "text-high" : "text-ink-3",
        className,
      )}
      title={source === "sla" ? "Set by SLA policy" : source === "manual" ? "Set manually" : undefined}
    >
      {overdue ? (
        <span className="rounded bg-critical/12 px-1 py-px">{-left}d overdue</span>
      ) : soon ? (
        `due in ${left}d`
      ) : (
        `due ${fmtDate(date)}`
      )}
      {source === "sla" && <span className="text-ink-3">· SLA</span>}
    </span>
  );
}
