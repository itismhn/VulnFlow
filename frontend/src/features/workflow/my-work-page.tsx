import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ClipboardList } from "lucide-react";
import { SeverityBadge, StatusBadge } from "@/components/severity";
import { Card, CardHeader, EmptyState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { FindingDrawer } from "@/features/findings/finding-drawer";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Finding, Page, RiskAcceptanceRow } from "@/lib/types";
import { cn, fmtDate, fmtNum } from "@/lib/utils";
import { DueDate } from "./due-date";

type Bucket = "overdue" | "week" | "later" | "none";

const BUCKETS: { key: Bucket; title: string; hint: string }[] = [
  { key: "overdue", title: "Overdue", hint: "Past the SLA or agreed date" },
  { key: "week", title: "Due in the next 7 days", hint: "Plan these this week" },
  { key: "later", title: "Later", hint: "On track" },
  { key: "none", title: "No due date", hint: "Informational or not covered by a policy" },
];

function bucketOf(f: Finding): Bucket {
  if (!f.due_date) return "none";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = (new Date(`${f.due_date}T00:00:00`).getTime() - today.getTime()) / 86_400_000;
  return days < 0 ? "overdue" : days <= 7 ? "week" : "later";
}

export function MyWorkPage({ finding }: { finding?: number }) {
  const { me } = useAuth();
  const navigate = useNavigate({ from: "/my-work" });
  const { data, isLoading } = useQuery({
    queryKey: ["findings", "mine", me?.id],
    queryFn: () =>
      api.get<Page<Finding>>("/findings", { assignee_id: me?.id, sort: "due_date", page_size: 500 }),
    enabled: !!me,
  });
  const { data: requests } = useQuery({
    queryKey: ["risk", "mine"],
    queryFn: () => api.get<Page<RiskAcceptanceRow>>("/risk-acceptances", { mine: true, status: ["pending"] }),
  });

  const items = data?.items ?? [];
  const groups = BUCKETS.map((b) => ({ ...b, items: items.filter((f) => bucketOf(f) === b.key) }));
  const open = (id: number) => navigate({ search: { finding: id } });

  return (
    <div className="animate-in">
      <PageHeader
        title="My work"
        description="Open findings assigned to you, ordered by deadline."
        actions={
          <Link
            to="/findings"
            search={{ assignee_id: me?.id }}
            className="text-sm text-brand hover:underline"
          >
            Open in findings explorer
          </Link>
        }
      />

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        {groups.map((g) => (
          <Card key={g.key} className="px-4 py-3">
            <div className="text-xs text-ink-3">{g.title}</div>
            <div
              className={cn(
                "num mt-1 font-display text-2xl font-semibold",
                g.key === "overdue" && g.items.length > 0 && "text-critical",
              )}
            >
              {isLoading ? "—" : fmtNum(g.items.length)}
            </div>
          </Card>
        ))}
      </div>

      {isLoading ? (
        <Skeleton className="h-64" />
      ) : items.length === 0 ? (
        <Card>
          <EmptyState icon={<ClipboardList className="size-8" />} title="Nothing assigned to you">
            Findings that someone assigns to you appear here with their deadlines. You also get a
            notification.
          </EmptyState>
        </Card>
      ) : (
        <div className="space-y-4">
          {groups
            .filter((g) => g.items.length)
            .map((g) => (
              <Card key={g.key} className="overflow-hidden">
                <CardHeader title={`${g.title} · ${g.items.length}`} description={g.hint} />
                <ul className="divide-y divide-line">
                  {g.items.map((f) => (
                    <li key={f.id}>
                      <button
                        type="button"
                        onClick={() => open(f.id)}
                        className="grid w-full grid-cols-[auto_1fr_auto] items-center gap-3 px-4 py-2.5 text-left transition hover:bg-surface-2/70 md:grid-cols-[90px_1fr_160px_110px_130px]"
                      >
                        <SeverityBadge severity={f.severity} />
                        <div className="min-w-0">
                          <div className="truncate text-sm">{f.plugin.name}</div>
                          <div className="truncate font-mono text-xs text-ink-3">
                            {f.asset.ip}:{f.port} {f.asset.hostname && `· ${f.asset.hostname}`}
                          </div>
                        </div>
                        <span className="hidden text-xs text-ink-3 md:block">
                          open since {fmtDate(f.first_seen)}
                        </span>
                        <span className="hidden md:block">
                          <StatusBadge status={f.status} />
                        </span>
                        <DueDate date={f.due_date} source={f.due_source} className="justify-self-end" />
                      </button>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
        </div>
      )}

      {!!requests?.items.length && (
        <Card className="mt-5 overflow-hidden">
          <CardHeader
            title="My pending risk requests"
            description="Waiting for an approver"
            actions={
              <Link to="/approvals" className="text-xs text-brand hover:underline">
                All requests
              </Link>
            }
          />
          <ul className="divide-y divide-line text-sm">
            {requests.items.map((r) => (
              <li key={r.id} className="flex items-center gap-3 px-4 py-2.5">
                <SeverityBadge severity={r.finding.severity} />
                <button
                  type="button"
                  onClick={() => open(r.finding_id)}
                  className="min-w-0 flex-1 truncate text-left hover:text-brand"
                >
                  {r.finding.plugin.name}{" "}
                  <span className="font-mono text-xs text-ink-3">{r.finding.asset.ip}</span>
                </button>
                <span className="text-xs text-ink-3">until {fmtDate(r.expires_at)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <FindingDrawer id={finding} onClose={() => navigate({ search: {} })} />
    </div>
  );
}
