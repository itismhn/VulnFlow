import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { Download, Layers, PackageSearch, RefreshCw, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { DropdownMenu, MenuItem } from "@/components/ui/overlay";
import {
  Badge,
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
import { useDebounced } from "@/lib/hooks";
import { useNetworks } from "@/lib/queries";
import type { SoftwareSearch } from "@/lib/search";
import type { Page, SoftwareCategory, SoftwareGroup, SoftwareInstance, SoftwareStats } from "@/lib/types";
import { cn, fmtDate, fmtNum } from "@/lib/utils";

export const CATEGORY_LABELS: Record<SoftwareCategory, string> = {
  os: "Operating system",
  application: "Application",
  package: "Package",
  service: "Network service",
  hardware: "Hardware",
};

const CATEGORY_TABS: { value: SoftwareCategory | undefined; label: string }[] = [
  { value: undefined, label: "All" },
  { value: "os", label: "Operating systems" },
  { value: "application", label: "Applications" },
  { value: "package", label: "Packages" },
  { value: "service", label: "Network services" },
  { value: "hardware", label: "Hardware" },
];

const PAGE_SIZE = 50;

/** Filters sent to the API (everything except view/sort/page). */
function apiFilters(s: SoftwareSearch) {
  return {
    q: s.q,
    category: s.category,
    vendor: s.vendor,
    product: s.product,
    version: s.version,
    network_id: s.network_id,
    ip: s.ip,
  };
}

export function SoftwarePage({ search }: { search: SoftwareSearch }) {
  const navigate = useNavigate({ from: "/software" });
  const { can } = useAuth();
  const qc = useQueryClient();
  const { data: networks = [] } = useNetworks();
  const view = search.view ?? "products";
  const page = search.page ?? 1;

  const patch = (next: Partial<SoftwareSearch>) =>
    navigate({ search: (prev) => ({ ...prev, page: undefined, ...next }), replace: true });

  // Text inputs update the URL after a short pause
  const [q, setQ] = useState(search.q ?? "");
  const [version, setVersion] = useState(search.version ?? "");
  const [ip, setIp] = useState(search.ip ?? "");
  const dq = useDebounced(q);
  const dversion = useDebounced(version, 400);
  const dip = useDebounced(ip, 500);
  useEffect(() => setQ(search.q ?? ""), [search.q]);
  useEffect(() => setVersion(search.version ?? ""), [search.version]);
  useEffect(() => setIp(search.ip ?? ""), [search.ip]);
  // biome-ignore lint/correctness/useExhaustiveDependencies: sync debounced inputs only
  useEffect(() => {
    if ((dq || undefined) !== search.q) patch({ q: dq || undefined });
  }, [dq]);
  // biome-ignore lint/correctness/useExhaustiveDependencies: sync debounced inputs only
  useEffect(() => {
    if ((dversion || undefined) !== search.version) patch({ version: dversion || undefined });
  }, [dversion]);
  // biome-ignore lint/correctness/useExhaustiveDependencies: sync debounced inputs only
  useEffect(() => {
    if ((dip || undefined) !== search.ip) patch({ ip: dip || undefined });
  }, [dip]);

  const filters = apiFilters(search);
  const { data: stats } = useQuery({
    queryKey: ["software", "stats"],
    queryFn: () => api.get<SoftwareStats>("/software/stats"),
  });
  const products = useQuery({
    queryKey: ["software", "products", filters, search.sort, page],
    queryFn: () =>
      api.get<Page<SoftwareGroup>>("/software", {
        ...filters,
        sort: search.sort,
        page,
        page_size: PAGE_SIZE,
      }),
    enabled: view === "products",
    placeholderData: keepPreviousData,
  });
  const hosts = useQuery({
    queryKey: ["software", "instances", filters, search.sort, page],
    queryFn: () =>
      api.get<Page<SoftwareInstance>>("/software/instances", {
        ...filters,
        sort: search.sort,
        page,
        page_size: PAGE_SIZE,
      }),
    enabled: view === "hosts",
    placeholderData: keepPreviousData,
  });
  const rebuild = useMutation({
    mutationFn: () => api.post("/software/rebuild"),
    onSuccess: () => {
      toast.success("Rebuilding the inventory from imported scans");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["software"] }), 3000);
    },
  });

  const exportUrl = (format: "csv" | "xlsx") => downloadUrl("/software/export", { ...filters, format });
  const active = view === "products" ? products : hosts;
  const empty = stats && stats.instances === 0;

  return (
    <div className="animate-in">
      <PageHeader
        title="Software inventory"
        description="Operating systems, applications, packages, and services that Nessus detected, with their versions. Search a product and a version range to find the hosts a CVE affects."
        actions={
          <>
            {can("settings:manage") && (
              <Button
                variant="ghost"
                onClick={() => rebuild.mutate()}
                disabled={rebuild.isPending}
                title="Re-read software versions from all imported scans"
              >
                <RefreshCw className={cn("size-4", rebuild.isPending && "animate-spin")} /> Rebuild
              </Button>
            )}
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
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-1.5" role="tablist" aria-label="Category">
        {CATEGORY_TABS.map((t) => {
          const selected = search.category === t.value;
          const count = t.value ? stats?.by_category[t.value] : stats?.products;
          if (t.value && !count && !selected) return null;
          return (
            <button
              key={t.label}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => patch({ category: t.value })}
              className={cn(
                "rounded-md border px-2.5 py-1 text-sm transition-colors",
                selected
                  ? "border-brand/40 bg-brand-soft text-brand"
                  : "border-line text-ink-2 hover:bg-surface-2",
              )}
            >
              {t.label}
              {count != null && <span className="num ml-1.5 text-xs text-ink-3">{fmtNum(count)}</span>}
            </button>
          );
        })}
        {stats && (
          <span className="ml-auto text-xs text-ink-3">
            {fmtNum(stats.instances)} installs on {fmtNum(stats.hosts)} hosts
          </span>
        )}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-ink-3" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Product, vendor or CPE, e.g. oracle"
            className="pl-8"
            aria-label="Search software"
          />
        </div>
        <Input
          value={version}
          onChange={(e) => setVersion(e.target.value)}
          placeholder="Version: 19.3, 2.4.*, <2.17.1"
          className="w-56 font-mono text-xs"
          aria-label="Version filter"
          title={
            "A plain version matches it and everything below it (19 matches 19.3.0.0).\n" +
            "Use <, <=, >, >=, = or != for ranges; combine them: >=2.0 <2.17.1"
          }
        />
        <Select
          value={search.network_id ?? ""}
          onChange={(e) => patch({ network_id: e.target.value ? Number(e.target.value) : undefined })}
          className="w-48"
          aria-label="Network"
        >
          <option value="">All networks</option>
          {networks.map((n) => (
            <option key={n.id} value={n.id}>
              {n.name}
            </option>
          ))}
        </Select>
        <Input
          value={ip}
          onChange={(e) => setIp(e.target.value)}
          placeholder="IP or CIDR"
          className="w-40 font-mono text-xs"
          aria-label="IP or CIDR"
        />
        <div className="ml-auto flex items-center gap-2">
          <div className="flex rounded-md border border-line p-0.5" role="group" aria-label="View">
            {(["products", "hosts"] as const).map((v) => (
              <button
                key={v}
                type="button"
                aria-pressed={view === v}
                onClick={() => patch({ view: v === "hosts" ? "hosts" : undefined, sort: undefined })}
                className={cn(
                  "rounded px-2.5 py-1 text-xs font-medium",
                  view === v ? "bg-surface-2 text-ink" : "text-ink-3 hover:text-ink",
                )}
              >
                {v === "products" ? "By product" : "By host"}
              </button>
            ))}
          </div>
          <Select
            value={search.sort ?? ""}
            onChange={(e) => patch({ sort: e.target.value || undefined })}
            className="w-40"
            aria-label="Sort"
          >
            {view === "products" ? (
              <>
                <option value="">Most hosts</option>
                <option value="-versions">Most versions</option>
                <option value="name">Name</option>
              </>
            ) : (
              <>
                <option value="">Software name</option>
                <option value="version">Oldest version</option>
                <option value="-version">Newest version</option>
                <option value="ip">IP address</option>
                <option value="-last_seen">Recently seen</option>
              </>
            )}
          </Select>
        </div>
      </div>

      {(search.product || search.vendor) && (
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-ink-3">Showing</span>
          <Badge tone="brand" className="text-xs">
            {search.vendor && <span className="text-brand/70">{search.vendor} /</span>}
            {search.product}
            <button
              type="button"
              aria-label="Clear product"
              onClick={() => patch({ product: undefined, vendor: undefined })}
              className="ml-0.5 hover:text-ink"
            >
              <X className="size-3" />
            </button>
          </Badge>
        </div>
      )}
      {active.error && <p className="mb-3 text-sm text-critical">{active.error.message}</p>}

      <Card className="overflow-hidden">
        {active.isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : empty ? (
          <EmptyState
            icon={<PackageSearch className="size-8" />}
            title="No software found yet"
            action={
              can("settings:manage") ? (
                <Button onClick={() => rebuild.mutate()} disabled={rebuild.isPending}>
                  <RefreshCw className="size-4" /> Build from imported scans
                </Button>
              ) : undefined
            }
          >
            Versions come from Nessus informational plugins, so import a scan. Credentialed scans report
            installed packages and software. Uncredentialed scans only report what services announce.
          </EmptyState>
        ) : view === "products" ? (
          <ProductsTable
            data={products.data}
            fetching={products.isFetching}
            onPick={(g, v) =>
              patch({
                view: "hosts",
                vendor: g.vendor,
                product: g.product,
                version: v === undefined || v === "" ? undefined : `=${v}`,
                sort: undefined,
              })
            }
          />
        ) : (
          <InstancesTable data={hosts.data} fetching={hosts.isFetching} />
        )}
        {active.data && active.data.total > 0 && (
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={active.data.total}
            onChange={(p) => navigate({ search: (prev) => ({ ...prev, page: p }) })}
          />
        )}
      </Card>
    </div>
  );
}

function ProductsTable({
  data,
  fetching,
  onPick,
}: {
  data: Page<SoftwareGroup> | undefined;
  fetching: boolean;
  onPick: (group: SoftwareGroup, version?: string) => void;
}) {
  if (!data?.items.length) {
    return <EmptyState icon={<Layers className="size-8" />} title="No software matches these filters" />;
  }
  return (
    <div className={cn("overflow-x-auto", fetching && "opacity-70")}>
      <table className="w-full text-sm">
        <thead className="bg-surface-2/60 text-left text-xs text-ink-3">
          <tr>
            <th className="px-4 py-2 font-medium">Software</th>
            <th className="px-4 py-2 font-medium">Versions found (hosts)</th>
            <th className="px-4 py-2 text-right font-medium">Hosts</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {data.items.map((g) => (
            <ProductRow key={`${g.vendor}|${g.product}`} group={g} onPick={onPick} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

const VISIBLE_VERSIONS = 8;

function ProductRow({
  group: g,
  onPick,
}: {
  group: SoftwareGroup;
  onPick: (group: SoftwareGroup, version?: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? g.versions : g.versions.slice(0, VISIBLE_VERSIONS);
  const hidden = g.version_count - shown.length;
  return (
    <tr className="align-top hover:bg-surface-2/60">
      <td className="max-w-sm px-4 py-2.5">
        <button type="button" onClick={() => onPick(g)} className="text-left font-medium hover:text-brand">
          {g.name}
        </button>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-3">
          <Badge className="text-[10px]">{CATEGORY_LABELS[g.category]}</Badge>
          {g.vendor && <span>{g.vendor}</span>}
          {g.cpe && <span className="font-mono">{g.cpe}</span>}
        </div>
      </td>
      <td className="px-4 py-2.5">
        <div className="flex flex-wrap gap-1">
          {shown.map((v) => (
            <button
              key={v.version}
              type="button"
              onClick={() => onPick(g, v.version)}
              title={`Show the ${v.hosts} host(s) running ${v.version || "an unknown version"}`}
              className="inline-flex items-center gap-1 rounded border border-line px-1.5 py-0.5 font-mono text-[11px] hover:border-brand/40 hover:bg-brand-soft hover:text-brand"
            >
              {v.version || <span className="font-sans text-ink-3 italic">unknown</span>}
              <span className="num text-ink-3">{v.hosts}</span>
            </button>
          ))}
          {hidden > 0 && !expanded && (
            <button
              type="button"
              onClick={() => setExpanded(true)}
              className="px-1 text-[11px] text-ink-3 hover:text-brand"
            >
              +{hidden} more
            </button>
          )}
        </div>
      </td>
      <td className="num px-4 py-2.5 text-right font-mono">
        <button type="button" onClick={() => onPick(g)} className="hover:text-brand">
          {fmtNum(g.hosts)}
        </button>
      </td>
    </tr>
  );
}

export function InstancesTable({
  data,
  fetching,
  showHost = true,
}: {
  data: Page<SoftwareInstance> | undefined;
  fetching: boolean;
  showHost?: boolean;
}) {
  if (!data?.items.length) {
    return <EmptyState icon={<Layers className="size-8" />} title="No software matches these filters" />;
  }
  return (
    <div className={cn("overflow-x-auto", fetching && "opacity-70")}>
      <table className="w-full text-sm">
        <thead className="bg-surface-2/60 text-left text-xs text-ink-3">
          <tr>
            {showHost && <th className="px-4 py-2 font-medium">Host</th>}
            <th className="px-4 py-2 font-medium">Software</th>
            <th className="px-4 py-2 font-medium">Version</th>
            <th className="px-4 py-2 font-medium">Where</th>
            <th className="px-4 py-2 font-medium">Source</th>
            <th className="px-4 py-2 font-medium">Last seen</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {data.items.map((s) => (
            <tr key={s.id} className="align-top hover:bg-surface-2/60">
              {showHost && (
                <td className="px-4 py-2">
                  <Link
                    to="/assets/$assetId"
                    params={{ assetId: String(s.asset_id) }}
                    className="font-mono hover:text-brand"
                  >
                    {s.ip}
                  </Link>
                  <div className="max-w-48 truncate text-xs text-ink-3">
                    {[s.hostname, s.network_name].filter(Boolean).join(" · ") || "—"}
                  </div>
                </td>
              )}
              <td className="max-w-xs px-4 py-2">
                <div className="truncate">{s.name}</div>
                <div className="text-[11px] text-ink-3">
                  {CATEGORY_LABELS[s.category]}
                  {s.vendor && ` · ${s.vendor}`}
                </div>
              </td>
              <td className="px-4 py-2 font-mono text-xs whitespace-nowrap">
                {s.version || <span className="font-sans text-ink-3 italic">unknown</span>}
              </td>
              <td className="max-w-xs px-4 py-2 text-xs text-ink-2">
                {s.port > 0 && (
                  <div className="font-mono">
                    {s.port}/{s.protocol}
                  </div>
                )}
                {s.path && (
                  <div className="truncate font-mono" title={s.path}>
                    {s.path}
                  </div>
                )}
                {s.cpe && (
                  <div className="truncate font-mono text-ink-3" title={s.cpe}>
                    {s.cpe}
                  </div>
                )}
                {!s.port && !s.path && !s.cpe && <span className="text-ink-3">—</span>}
              </td>
              <td className="px-4 py-2 text-xs">
                {s.plugin_id ? (
                  <Link
                    to="/vulnerabilities/$pluginId"
                    params={{ pluginId: String(s.plugin_id) }}
                    className="font-mono text-ink-2 hover:text-brand"
                  >
                    <span className="whitespace-nowrap">Plugin {s.plugin_id}</span>
                  </Link>
                ) : (
                  <span className="text-ink-3">Host properties</span>
                )}
              </td>
              <td className="px-4 py-2 text-xs whitespace-nowrap text-ink-2">{fmtDate(s.last_seen)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
