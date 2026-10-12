import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ArrowRight, GitCompare } from "lucide-react";
import { SeverityBadge, StatusBadge } from "@/components/severity";
import { Card, EmptyState, PageHeader, Pagination, Select, Skeleton } from "@/components/ui/primitives";
import { FindingDrawer } from "@/features/findings/finding-drawer";
import { api } from "@/lib/api";
import type { Finding, Page, Scan, ScanDiff } from "@/lib/types";
import { cn, fmtDate, fmtNum } from "@/lib/utils";

export interface CompareSearch {
  base?: number;
  compare?: number;
  kind?: "new" | "fixed" | "persisting";
  page?: number;
  finding?: number;
}

const KINDS = [
  { key: "new", label: "New", hint: "Found in the newer scan only", tone: "text-critical" },
  { key: "fixed", label: "Fixed", hint: "Gone in the newer scan", tone: "text-ok" },
  { key: "persisting", label: "Persisting", hint: "Present in both", tone: "text-ink" },
] as const;

const PAGE_SIZE = 50;

export function ComparePage({ search }: { search: CompareSearch }) {
  const navigate = useNavigate({ from: "/scans/compare" });
  const kind = search.kind ?? "new";
  const page = search.page ?? 1;
  const set = (patch: Partial<CompareSearch>) =>
    navigate({ search: (prev: CompareSearch) => ({ ...prev, page: undefined, ...patch }) });

  const { data: scans } = useQuery({
    queryKey: ["scans", "all-done"],
    queryFn: () => api.get<Page<Scan>>("/scans", { status: "done", page_size: 200 }),
  });
  const ready = !!search.base && !!search.compare && search.base !== search.compare;
  const { data: diff } = useQuery({
    queryKey: ["scans", "diff", search.compare, search.base],
    queryFn: () => api.get<ScanDiff>(`/scans/${search.compare}/diff`, { against: search.base }),
    enabled: ready,
  });
  const list = useQuery({
    queryKey: ["scans", "diff-findings", search.compare, search.base, kind, page],
    queryFn: () =>
      api.get<Page<Finding>>(`/scans/${search.compare}/diff/findings`, {
        against: search.base,
        kind,
        page,
        page_size: PAGE_SIZE,
      }),
    enabled: ready,
    placeholderData: keepPreviousData,
  });

  const options = scans?.items ?? [];
  const scanSelect = (value: number | undefined, onChange: (id: number) => void, label: string) => (
    <Select
      value={value ?? ""}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-full sm:w-72"
      aria-label={label}
    >
      <option value="">{label}…</option>
      {options.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name} · {fmtDate(s.started_at)}
        </option>
      ))}
    </Select>
  );

  return (
    <div className="animate-in">
      <PageHeader
        eyebrow="Scan history"
        title="Compare scans"
        description="What changed between two scans, on the hosts both of them covered. Informational findings are left out."
      />
      <Card className="mb-4 flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        {scanSelect(search.base, (id) => set({ base: id }), "Older scan")}
        <ArrowRight className="hidden size-4 shrink-0 text-ink-3 sm:block" />
        {scanSelect(search.compare, (id) => set({ compare: id }), "Newer scan")}
      </Card>

      {!ready ? (
        <Card>
          <EmptyState icon={<GitCompare className="size-8" />} title="Pick two scans">
            Choose an older and a newer scan of the same hosts to see new, fixed and persisting findings.
          </EmptyState>
        </Card>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-3 gap-3">
            {KINDS.map((k) => (
              <button
                key={k.key}
                type="button"
                onClick={() => set({ kind: k.key })}
                aria-pressed={kind === k.key}
                className={cn(
                  "rounded-lg border bg-surface px-4 py-3 text-left transition",
                  kind === k.key ? "border-brand ring-2 ring-brand/15" : "border-line hover:border-ink-3/40",
                )}
              >
                <div className="text-xs text-ink-3">{k.label}</div>
                <div className={cn("num mt-1 font-display text-2xl font-semibold", k.tone)}>
                  {diff ? fmtNum(diff[k.key]) : "—"}
                </div>
                <div className="hidden text-[11px] text-ink-3 sm:block">{k.hint}</div>
              </button>
            ))}
          </div>
          <Card className="overflow-hidden">
            {list.isLoading ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 6 }, (_, i) => (
                  <Skeleton key={i} className="h-10" />
                ))}
              </div>
            ) : !list.data?.items.length ? (
              <EmptyState title={`No ${kind} findings`}>
                Nothing in this group between these two scans.
              </EmptyState>
            ) : (
              <ul className={cn("divide-y divide-line", list.isFetching && "opacity-70")}>
                {list.data.items.map((f) => (
                  <li key={f.id}>
                    <button
                      type="button"
                      onClick={() => set({ finding: f.id, page })}
                      className="grid w-full grid-cols-[auto_1fr_auto] items-center gap-3 px-4 py-2.5 text-left transition hover:bg-surface-2/70"
                    >
                      <SeverityBadge severity={f.severity} />
                      <div className="min-w-0">
                        <div className="truncate text-sm">{f.plugin.name}</div>
                        <div className="truncate font-mono text-xs text-ink-3">
                          {f.asset.ip}:{f.port}/{f.protocol} {f.asset.hostname && `· ${f.asset.hostname}`}
                        </div>
                      </div>
                      <StatusBadge status={f.status} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {list.data && (
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={list.data.total}
                onChange={(p) => set({ page: p })}
              />
            )}
          </Card>
        </>
      )}
      <FindingDrawer
        id={search.finding}
        onClose={() => navigate({ search: (prev: CompareSearch) => ({ ...prev, finding: undefined }) })}
      />
    </div>
  );
}
