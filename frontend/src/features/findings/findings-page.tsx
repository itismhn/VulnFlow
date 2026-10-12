import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ArrowDown, ArrowUp, ChevronRight, Download, FileText, Flame, ListChecks } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { SeverityBadge, SeverityCounters, SeverityStrip, StatusBadge } from "@/components/severity";
import { DropdownMenu, MenuItem } from "@/components/ui/overlay";
import {
  Button,
  Card,
  EmptyState,
  Input,
  PageHeader,
  Pagination,
  Select,
  Skeleton,
} from "@/components/ui/primitives";
import { api, downloadUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useDirectory } from "@/lib/queries";
import { type FindingsSearch, filtersOf, hasFilters } from "@/lib/search";
import type { Finding, FindingGroup, FindingStatus, GroupBy, Page } from "@/lib/types";
import { cn, daysSince, fmtDate, fmtNum, STATUS_LABELS } from "@/lib/utils";
import { ActiveFilterChips, FilterBar } from "./filter-bar";
import { FindingDrawer } from "./finding-drawer";

const PAGE_SIZE = 50;

const GROUPS: { value: GroupBy | ""; label: string }[] = [
  { value: "", label: "Findings" },
  { value: "host", label: "Host" },
  { value: "plugin", label: "Vulnerability" },
  { value: "network", label: "Network" },
  { value: "zone", label: "Zone" },
  { value: "port", label: "Port" },
];

/** Applying a group row narrows the filter to that group and returns to the list view. */
function drillDown(group: GroupBy, key: string): Partial<FindingsSearch> {
  switch (group) {
    case "host":
      return { asset_id: Number(key) };
    case "plugin":
      return { plugin_id: [Number(key)] };
    case "network":
      return Number(key) ? { network_id: [Number(key)] } : {};
    case "zone":
      return { zone: [key] };
    case "severity":
      return { severity: [Number(key)] };
    case "status":
      return { status: [key as FindingStatus] };
    case "port":
      return { port: Number(key.split("/")[0]) };
  }
}

export function FindingsPage({ search }: { search: FindingsSearch }) {
  const navigate = useNavigate({ from: "/findings" });
  const { can } = useAuth();
  const filters = filtersOf(search);
  const page = search.page ?? 1;
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const patch = (p: Partial<FindingsSearch>) => {
    setSelected(new Set());
    navigate({
      search: (prev: FindingsSearch) => ({ ...prev, ...p, page: "page" in p ? p.page : undefined }),
    });
  };

  const list = useQuery({
    queryKey: ["findings", "list", filters, search.sort, page],
    queryFn: () =>
      api.get<Page<Finding>>("/findings", {
        ...filters,
        sort: search.sort,
        page,
        page_size: PAGE_SIZE,
      } as never),
    enabled: !search.group,
    placeholderData: keepPreviousData,
  });
  const groups = useQuery({
    queryKey: ["findings", "groups", search.group, filters, page],
    queryFn: () =>
      api.get<Page<FindingGroup>>("/findings/groups", {
        ...filters,
        by: search.group,
        page,
        page_size: PAGE_SIZE,
      } as never),
    enabled: !!search.group,
    placeholderData: keepPreviousData,
  });

  const exportUrl = (format: "csv" | "xlsx") =>
    downloadUrl("/findings/export", { ...filters, sort: search.sort, format } as never);

  return (
    <div className="animate-in">
      <PageHeader
        title="Findings"
        description="Every vulnerability instance on every host, tracked across scans."
        actions={
          <>
            <DropdownMenu
              trigger={
                <Button>
                  <Download className="size-4" /> Export
                </Button>
              }
            >
              <MenuItem onSelect={() => window.location.assign(exportUrl("csv"))}>Export as CSV</MenuItem>
              <MenuItem onSelect={() => window.location.assign(exportUrl("xlsx"))}>
                Export as Excel (.xlsx)
              </MenuItem>
            </DropdownMenu>
            <Button
              onClick={() => navigate({ to: "/reports", search: { filters: JSON.stringify(filters) } })}
            >
              <FileText className="size-4" /> Report from this view
            </Button>
          </>
        }
      />

      <div className="mb-3 space-y-2.5">
        <FilterBar search={search} patch={patch} />
        {hasFilters(filters) && (
          <ActiveFilterChips
            search={search}
            patch={patch}
            onClear={() => navigate({ search: { group: search.group } })}
          />
        )}
      </div>

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
          <div className="flex items-center gap-1 text-xs" role="tablist" aria-label="Group findings by">
            <span className="mr-1 text-ink-3">View by</span>
            {GROUPS.map((g) => (
              <button
                key={g.value}
                type="button"
                role="tab"
                aria-selected={(search.group ?? "") === g.value}
                onClick={() => patch({ group: g.value || undefined, page: undefined })}
                className={cn(
                  "rounded-md px-2.5 py-1 font-medium transition",
                  (search.group ?? "") === g.value
                    ? "bg-brand-soft text-brand"
                    : "text-ink-2 hover:bg-surface-2",
                )}
              >
                {g.label}
              </button>
            ))}
          </div>
          <span className="num text-xs text-ink-3">
            {search.group
              ? `${fmtNum(groups.data?.total ?? 0)} groups`
              : `${fmtNum(list.data?.total ?? 0)} findings`}
          </span>
        </div>

        {selected.size > 0 && can("findings:update") && (
          <BulkBar ids={[...selected]} onDone={() => setSelected(new Set())} />
        )}

        {search.group ? (
          <GroupList
            query={groups}
            group={search.group}
            onPick={(key) => patch({ ...drillDown(search.group as GroupBy, key), group: undefined })}
          />
        ) : (
          <FindingTable
            query={list}
            sort={search.sort}
            onSort={(sort) => patch({ sort })}
            selected={selected}
            setSelected={setSelected}
            selectable={can("findings:update")}
            onOpen={(id) => navigate({ search: (prev: FindingsSearch) => ({ ...prev, finding: id }) })}
            onClear={() => navigate({ search: {} })}
          />
        )}

        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={(search.group ? groups.data?.total : list.data?.total) ?? 0}
          onChange={(p) => patch({ page: p })}
        />
      </Card>

      <FindingDrawer
        id={search.finding}
        onClose={() => navigate({ search: (prev: FindingsSearch) => ({ ...prev, finding: undefined }) })}
      />
    </div>
  );
}

function SortHeader({
  label,
  field,
  sort,
  onSort,
  className,
}: {
  label: string;
  field: string;
  sort?: string;
  onSort: (s: string) => void;
  className?: string;
}) {
  const active = (sort ?? "-severity").replace("-", "") === field;
  const desc = (sort ?? "-severity").startsWith("-");
  return (
    <th className={cn("px-3 py-2 font-medium", className)}>
      <button
        type="button"
        onClick={() => onSort(active && desc ? field : `-${field}`)}
        className={cn("inline-flex items-center gap-1 hover:text-ink", active && "text-ink")}
      >
        {label}
        {active && (desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
      </button>
    </th>
  );
}

function FindingTable({
  query,
  sort,
  onSort,
  selected,
  setSelected,
  selectable,
  onOpen,
  onClear,
}: {
  query: ReturnType<typeof useQuery<Page<Finding>>>;
  sort?: string;
  onSort: (s: string) => void;
  selected: Set<number>;
  setSelected: (s: Set<number>) => void;
  selectable: boolean;
  onOpen: (id: number) => void;
  onClear: () => void;
}) {
  const items = query.data?.items ?? [];
  if (query.isLoading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-8" />
        ))}
      </div>
    );
  }
  if (!items.length) {
    return (
      <EmptyState
        icon={<ListChecks className="size-8" />}
        title="No findings match these filters"
        action={
          <Button size="sm" onClick={onClear}>
            Clear filters
          </Button>
        }
      >
        Try a wider IP range, another status, or include informational findings.
      </EmptyState>
    );
  }
  const allOnPage = items.every((f) => selected.has(f.id));
  return (
    <div className={cn("overflow-x-auto transition-opacity", query.isFetching && "opacity-70")}>
      <table className="w-full text-sm">
        <thead className="bg-surface-2/60 text-left text-xs text-ink-3">
          <tr>
            {selectable && (
              <th className="w-8 px-3 py-2">
                <input
                  type="checkbox"
                  aria-label="Select all on this page"
                  className="accent-[var(--brand)]"
                  checked={allOnPage}
                  onChange={() => {
                    const next = new Set(selected);
                    for (const f of items) {
                      if (allOnPage) next.delete(f.id);
                      else next.add(f.id);
                    }
                    setSelected(next);
                  }}
                />
              </th>
            )}
            <SortHeader label="Severity" field="severity" sort={sort} onSort={onSort} />
            <SortHeader label="Vulnerability" field="plugin" sort={sort} onSort={onSort} />
            <SortHeader label="Host" field="ip" sort={sort} onSort={onSort} />
            <SortHeader label="Port" field="port" sort={sort} onSort={onSort} />
            <SortHeader label="CVSS" field="cvss" sort={sort} onSort={onSort} />
            <SortHeader label="Status" field="status" sort={sort} onSort={onSort} />
            <SortHeader
              label="First seen"
              field="first_seen"
              sort={sort}
              onSort={onSort}
              className="whitespace-nowrap"
            />
            <th className="px-3 py-2 font-medium">Assignee</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.map((f) => (
            <tr
              key={f.id}
              onClick={() => onOpen(f.id)}
              className={cn(
                "cursor-pointer transition hover:bg-surface-2/70",
                selected.has(f.id) && "bg-brand-soft/50",
              )}
            >
              {selectable && (
                <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    aria-label={`Select finding ${f.id}`}
                    className="accent-[var(--brand)]"
                    checked={selected.has(f.id)}
                    onChange={() => {
                      const next = new Set(selected);
                      if (next.has(f.id)) next.delete(f.id);
                      else next.add(f.id);
                      setSelected(next);
                    }}
                  />
                </td>
              )}
              <td className="px-3 py-2">
                <SeverityBadge severity={f.severity} />
              </td>
              <td className="max-w-md px-3 py-2">
                <div className="flex items-center gap-1.5">
                  {f.plugin.exploit_available && (
                    <Flame className="size-3.5 shrink-0 text-critical" aria-label="Exploit available" />
                  )}
                  <span className="truncate">{f.plugin.name}</span>
                </div>
                <div className="font-mono text-[11px] text-ink-3">
                  {f.plugin.id}
                  {f.plugin.cves.length > 0 &&
                    ` · ${f.plugin.cves[0]}${f.plugin.cves.length > 1 ? ` +${f.plugin.cves.length - 1}` : ""}`}
                </div>
              </td>
              <td className="px-3 py-2">
                <div className="font-mono text-[13px]">{f.asset.ip}</div>
                <div className="max-w-40 truncate text-[11px] text-ink-3">
                  {f.asset.hostname || f.asset.fqdn}
                </div>
              </td>
              <td className="px-3 py-2 font-mono text-xs text-ink-2">
                {f.port}/{f.protocol}
              </td>
              <td className="num px-3 py-2 font-mono text-xs">{f.plugin.cvss3_base ?? "—"}</td>
              <td className="px-3 py-2">
                <StatusBadge status={f.status} />
              </td>
              <td className="px-3 py-2 text-xs whitespace-nowrap text-ink-2">
                {fmtDate(f.first_seen)}
                <div className="text-[11px] text-ink-3">{daysSince(f.first_seen)}d open</div>
              </td>
              <td className="px-3 py-2 text-xs text-ink-2">
                {f.assignee?.username ?? <span className="text-ink-3">—</span>}
                {f.due_date && (
                  <div
                    className={cn(
                      "text-[11px]",
                      new Date(f.due_date) < new Date() ? "text-critical" : "text-ink-3",
                    )}
                  >
                    due {fmtDate(f.due_date)}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GroupList({
  query,
  group,
  onPick,
}: {
  query: ReturnType<typeof useQuery<Page<FindingGroup>>>;
  group: GroupBy;
  onPick: (key: string) => void;
}) {
  const items = query.data?.items ?? [];
  if (query.isLoading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-10" />
        ))}
      </div>
    );
  }
  if (!items.length)
    return <EmptyState title="Nothing to group">No findings match these filters.</EmptyState>;
  const mono = group === "host" || group === "port";
  return (
    <ul className={cn("divide-y divide-line transition-opacity", query.isFetching && "opacity-70")}>
      <li className="hidden grid-cols-[1fr_180px_200px_80px_20px] gap-4 bg-surface-2/60 px-4 py-2 text-xs text-ink-3 md:grid">
        <span>{GROUPS.find((g) => g.value === group)?.label}</span>
        <span>Severity mix</span>
        <span className="flex gap-3 font-mono">
          <span className="w-8 text-right">C</span>
          <span className="w-8 text-right">H</span>
          <span className="w-8 text-right">M</span>
          <span className="w-8 text-right">L</span>
        </span>
        <span className="text-right">Total</span>
        <span />
      </li>
      {items.map((g) => (
        <li key={g.key}>
          <button
            type="button"
            onClick={() => onPick(g.key)}
            className="grid w-full grid-cols-[1fr_auto] items-center gap-4 px-4 py-2.5 text-left transition hover:bg-surface-2/70 md:grid-cols-[1fr_180px_200px_80px_20px]"
          >
            <div className="min-w-0">
              <div className={cn("truncate text-sm", mono && "font-mono")}>{g.label}</div>
              {g.sublabel && <div className="truncate text-xs text-ink-3">{g.sublabel}</div>}
            </div>
            <SeverityStrip counts={g} className="hidden md:flex" />
            <SeverityCounters counts={g} className="hidden md:flex" />
            <span className="num text-right font-mono text-sm">{fmtNum(g.total)}</span>
            <ChevronRight className="hidden size-4 text-ink-3 md:block" />
          </button>
        </li>
      ))}
    </ul>
  );
}

function BulkBar({ ids, onDone }: { ids: number[]; onDone: () => void }) {
  const qc = useQueryClient();
  const { data: users = [] } = useDirectory();
  const [status, setStatus] = useState<FindingStatus | "">("");
  const [assignee, setAssignee] = useState("");
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");
  const needsNote = status === "risk_accepted" || status === "false_positive";
  const apply = useMutation({
    mutationFn: () =>
      api.post<{ updated: number }>("/findings/bulk", {
        ids,
        status: status || undefined,
        assignee_id: assignee && assignee !== "none" ? Number(assignee) : undefined,
        clear_assignee: assignee === "none",
        due_date: due || undefined,
        note,
      }),
    onSuccess: (r) => {
      toast.success(`Updated ${r.updated} findings`);
      qc.invalidateQueries({ queryKey: ["findings"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onDone();
    },
  });
  return (
    <div className="animate-in flex flex-wrap items-center gap-2 border-b border-line bg-brand-soft/60 px-3 py-2">
      <span className="text-sm font-medium">{ids.length} selected</span>
      <Select
        value={status}
        onChange={(e) => setStatus(e.target.value as FindingStatus)}
        className="h-8 w-40 text-xs"
      >
        <option value="">Keep status</option>
        {(Object.keys(STATUS_LABELS) as FindingStatus[]).map((s) => (
          <option key={s} value={s}>
            {STATUS_LABELS[s]}
          </option>
        ))}
      </Select>
      <Select value={assignee} onChange={(e) => setAssignee(e.target.value)} className="h-8 w-40 text-xs">
        <option value="">Keep assignee</option>
        <option value="none">Unassign</option>
        {users.map((u) => (
          <option key={u.id} value={u.id}>
            {u.full_name || u.username}
          </option>
        ))}
      </Select>
      <Input
        type="date"
        value={due}
        onChange={(e) => setDue(e.target.value)}
        className="h-8 w-40 text-xs"
        aria-label="Due date"
      />
      <Input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder={needsNote ? "Justification (required)" : "Note (optional)"}
        className="h-8 min-w-48 flex-1 text-xs"
      />
      <Button
        size="sm"
        variant="primary"
        disabled={(!status && !assignee && !due && !note.trim()) || (needsNote && !note.trim())}
        loading={apply.isPending}
        onClick={() => apply.mutate()}
      >
        Apply
      </Button>
      <Button size="sm" variant="ghost" onClick={onDone}>
        Cancel
      </Button>
    </div>
  );
}
