import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Boxes, Search } from "lucide-react";
import { useState } from "react";
import { SeverityCounters, SeverityStrip } from "@/components/severity";
import {
  Card,
  EmptyState,
  Input,
  PageHeader,
  Pagination,
  Select,
  Skeleton,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useDebounced } from "@/lib/hooks";
import { useNetworks } from "@/lib/queries";
import type { AssetRow, Page } from "@/lib/types";
import { cn, fmtDate } from "@/lib/utils";

export function CriticalityDots({ value }: { value: number }) {
  return (
    <span
      role="img"
      className="inline-flex gap-0.5"
      title={`Criticality ${value} of 5`}
      aria-label={`Criticality ${value} of 5`}
    >
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={cn("h-2.5 w-1 rounded-sm", i <= value ? "bg-ink-2" : "bg-line")} />
      ))}
    </span>
  );
}

export function AssetsPage() {
  const [q, setQ] = useState("");
  const [ip, setIp] = useState("");
  const [networkId, setNetworkId] = useState("");
  const [onlyFindings, setOnlyFindings] = useState(false);
  const [unassigned, setUnassigned] = useState(false);
  const [sort, setSort] = useState("-risk");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const dip = useDebounced(ip, 500);
  const { data: networks = [] } = useNetworks();
  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ["assets", dq, dip, networkId, onlyFindings, unassigned, sort, page],
    queryFn: () =>
      api.get<Page<AssetRow>>("/assets", {
        q: dq,
        ip: dip,
        network_id: networkId,
        with_findings: onlyFindings || undefined,
        unassigned: unassigned || undefined,
        sort,
        page,
        page_size: 50,
      }),
    placeholderData: keepPreviousData,
  });
  const reset =
    <T,>(fn: (v: T) => void) =>
    (v: T) => {
      fn(v);
      setPage(1);
    };

  return (
    <div className="animate-in">
      <PageHeader
        title="Assets"
        description="Every host seen in any scan, ranked by risk: open findings weighted by severity and the asset's criticality."
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-ink-3" />
          <Input
            value={q}
            onChange={(e) => reset(setQ)(e.target.value)}
            placeholder="Hostname, IP, OS…"
            className="pl-8"
          />
        </div>
        <Input
          value={ip}
          onChange={(e) => reset(setIp)(e.target.value)}
          placeholder="CIDR, e.g. 10.40.0.0/22"
          className="w-52 font-mono text-xs"
        />
        <Select value={networkId} onChange={(e) => reset(setNetworkId)(e.target.value)} className="w-52">
          <option value="">All networks</option>
          {networks.map((n) => (
            <option key={n.id} value={n.id}>
              {n.name}
            </option>
          ))}
        </Select>
        <Select value={sort} onChange={(e) => setSort(e.target.value)} className="w-44" aria-label="Sort">
          <option value="-risk">Highest risk</option>
          <option value="-critical">Most critical</option>
          <option value="ip">IP address</option>
          <option value="-last_seen">Recently seen</option>
        </Select>
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input
            type="checkbox"
            className="accent-[var(--brand)]"
            checked={onlyFindings}
            onChange={(e) => reset(setOnlyFindings)(e.target.checked)}
          />
          With open findings
        </label>
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input
            type="checkbox"
            className="accent-[var(--brand)]"
            checked={unassigned}
            onChange={(e) => reset(setUnassigned)(e.target.checked)}
          />
          Not in any network
        </label>
      </div>
      {error && <p className="mb-3 text-sm text-critical">{error.message}</p>}

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : !data?.items.length ? (
          <EmptyState icon={<Boxes className="size-8" />} title="No assets match">
            Assets are created automatically from imported scans.
          </EmptyState>
        ) : (
          <div className={cn("overflow-x-auto", isFetching && "opacity-70")}>
            <table className="w-full text-sm">
              <thead className="bg-surface-2/60 text-left text-xs text-ink-3">
                <tr>
                  <th className="px-4 py-2 font-medium">Host</th>
                  <th className="px-4 py-2 font-medium">Network</th>
                  <th className="px-4 py-2 font-medium">Operating system</th>
                  <th className="px-4 py-2 font-medium">Criticality</th>
                  <th className="w-36 px-4 py-2 font-medium">Open findings</th>
                  <th className="px-4 py-2 font-medium">C / H / M / L</th>
                  <th className="px-4 py-2 text-right font-medium">Risk</th>
                  <th className="px-4 py-2 font-medium">Last seen</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.items.map((a) => (
                  <tr key={a.id} className="hover:bg-surface-2/60">
                    <td className="px-4 py-2">
                      <Link
                        to="/assets/$assetId"
                        params={{ assetId: String(a.id) }}
                        className="font-mono hover:text-brand"
                      >
                        {a.ip}
                      </Link>
                      <div className="max-w-48 truncate text-xs text-ink-3">
                        {a.hostname || a.fqdn || a.netbios || "—"}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-xs">
                      {a.network_name ?? <span className="text-ink-3">Unassigned</span>}
                      {a.zone && <div className="text-ink-3">{a.zone}</div>}
                    </td>
                    <td className="max-w-56 truncate px-4 py-2 text-xs text-ink-2">{a.os || "—"}</td>
                    <td className="px-4 py-2">
                      <CriticalityDots value={a.effective_criticality} />
                    </td>
                    <td className="px-4 py-2">
                      <SeverityStrip counts={a.open} />
                    </td>
                    <td className="px-4 py-2">
                      <SeverityCounters counts={a.open} />
                    </td>
                    <td className="num px-4 py-2 text-right font-mono font-medium">{a.risk_score}</td>
                    <td className="px-4 py-2 text-xs text-ink-2">{fmtDate(a.last_seen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && data.total > 0 && (
          <Pagination page={page} pageSize={50} total={data.total} onChange={setPage} />
        )}
      </Card>
    </div>
  );
}
