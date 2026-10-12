import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { AlertTriangle, Archive, GitCompare, Loader2, ScanLine, Search } from "lucide-react";
import { useState } from "react";
import { SeverityCounters, SeverityStrip } from "@/components/severity";
import { Badge, Card, EmptyState, Input, PageHeader, Pagination, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useDebounced } from "@/lib/hooks";
import type { Page, Scan } from "@/lib/types";
import { cn, fmtBytes, fmtDate, fmtNum, scanCounts } from "@/lib/utils";

export function ScanStatusBadge({ scan }: { scan: Scan }) {
  if (scan.status === "done") return null;
  if (scan.status === "failed")
    return (
      <Badge tone="danger">
        <AlertTriangle className="size-3" /> Failed
      </Badge>
    );
  return (
    <Badge tone="brand">
      <Loader2 className="size-3 animate-spin" />
      {scan.status === "queued" ? "Queued" : `Importing ${scan.progress}%`}
    </Badge>
  );
}

export function ScansPage() {
  const [q, setQ] = useState("");
  const [archived, setArchived] = useState(false);
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const { data, isLoading } = useQuery({
    queryKey: ["scans", dq, archived, page],
    queryFn: () => api.get<Page<Scan>>("/scans", { q: dq, archived, page, page_size: 25 }),
    placeholderData: keepPreviousData,
    // Poll while anything is still importing
    refetchInterval: (query) =>
      query.state.data?.items.some((s) => s.status === "queued" || s.status === "parsing") ? 2000 : false,
  });

  return (
    <div className="animate-in">
      <PageHeader
        title="Scan history"
        description="Every imported scan, newest first. Each import updates finding status for the hosts it covered."
        actions={
          <Link
            to="/scans/compare"
            className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-surface px-3.5 text-sm font-medium transition hover:bg-surface-2"
          >
            <GitCompare className="size-4" /> Compare scans
          </Link>
        }
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-80">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-ink-3" />
          <Input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder="Search by name, file or policy"
            className="pl-8"
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input
            type="checkbox"
            className="accent-[var(--brand)]"
            checked={archived}
            onChange={(e) => {
              setArchived(e.target.checked);
              setPage(1);
            }}
          />
          <Archive className="size-3.5" /> Show archived
        </label>
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        ) : !data?.items.length ? (
          <EmptyState
            icon={<ScanLine className="size-8" />}
            title={archived ? "No archived scans" : "No scans yet"}
          >
            {archived
              ? "Archived scans appear here."
              : "Use “Import scan” in the top bar to upload a .nessus export."}
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface-2/60 text-left text-xs text-ink-3">
                <tr>
                  <th className="px-4 py-2 font-medium">Scan</th>
                  <th className="px-4 py-2 font-medium">Scanned</th>
                  <th className="px-4 py-2 text-right font-medium">Hosts</th>
                  <th className="w-44 px-4 py-2 font-medium">Severity mix</th>
                  <th className="px-4 py-2 font-medium">
                    <span className="flex gap-3 font-mono">
                      <span className="w-8 text-right">C</span>
                      <span className="w-8 text-right">H</span>
                      <span className="w-8 text-right">M</span>
                      <span className="w-8 text-right">L</span>
                    </span>
                  </th>
                  <th className="px-4 py-2 font-medium">Change</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.items.map((s) => (
                  <tr key={s.id} className="hover:bg-surface-2/60">
                    <td className="max-w-sm px-4 py-2.5">
                      <Link
                        to="/scans/$scanId"
                        params={{ scanId: String(s.id) }}
                        className="font-medium hover:text-brand"
                      >
                        {s.name}
                      </Link>
                      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-ink-3">
                        <span className="truncate">{s.policy_name || s.filename}</span>
                        <span>· {fmtBytes(s.size_bytes)}</span>
                        <ScanStatusBadge scan={s} />
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-xs whitespace-nowrap text-ink-2">
                      {fmtDate(s.started_at, true)}
                      <div className="text-ink-3">by {s.uploaded_by?.username ?? "—"}</div>
                    </td>
                    <td className="num px-4 py-2.5 text-right font-mono">{fmtNum(s.host_count)}</td>
                    <td className="px-4 py-2.5">
                      <SeverityStrip counts={scanCounts(s)} />
                    </td>
                    <td className="px-4 py-2.5">
                      <SeverityCounters counts={scanCounts(s)} />
                    </td>
                    <td className="px-4 py-2.5 text-xs whitespace-nowrap">
                      {s.status === "done" ? (
                        <span className="num flex gap-2 font-mono">
                          <span className={cn(s.new_count ? "text-critical" : "text-ink-3")}>
                            +{s.new_count} new
                          </span>
                          <span className={cn(s.fixed_count ? "text-ok" : "text-ink-3")}>
                            −{s.fixed_count} fixed
                          </span>
                          {s.reopened_count > 0 && <span className="text-high">↺{s.reopened_count}</span>}
                        </span>
                      ) : (
                        <span className="text-ink-3">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && data.total > 0 && (
          <Pagination page={page} pageSize={25} total={data.total} onChange={setPage} />
        )}
      </Card>
    </div>
  );
}
