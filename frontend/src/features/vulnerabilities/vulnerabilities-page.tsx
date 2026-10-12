import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Bug, Flame, Search } from "lucide-react";
import { useState } from "react";
import { SeverityBadge } from "@/components/severity";
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
import { api } from "@/lib/api";
import { useDebounced } from "@/lib/hooks";
import type { Page, VulnRow } from "@/lib/types";
import { cn, fmtNum } from "@/lib/utils";

export function VulnerabilitiesPage() {
  const [q, setQ] = useState("");
  const [severity, setSeverity] = useState("");
  const [exploitable, setExploitable] = useState(false);
  const [sort, setSort] = useState("-severity");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["vulns", dq, severity, exploitable, sort, page],
    queryFn: () =>
      api.get<Page<VulnRow>>("/vulnerabilities", {
        q: dq,
        severity: severity ? [Number(severity)] : undefined,
        exploitable: exploitable || undefined,
        sort,
        page,
        page_size: 50,
      }),
    placeholderData: keepPreviousData,
  });

  return (
    <div className="animate-in">
      <PageHeader
        title="Vulnerabilities"
        description="Open findings grouped by vulnerability. Answers “where is this CVE across the estate?”"
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
            placeholder="Name, CVE or plugin ID"
            className="pl-8"
          />
        </div>
        <Select value={severity} onChange={(e) => setSeverity(e.target.value)} className="w-40">
          <option value="">All severities</option>
          <option value="4">Critical</option>
          <option value="3">High</option>
          <option value="2">Medium</option>
          <option value="1">Low</option>
        </Select>
        <Select value={sort} onChange={(e) => setSort(e.target.value)} className="w-44">
          <option value="-severity">Severity</option>
          <option value="-hosts">Most hosts</option>
          <option value="-cvss">CVSS</option>
          <option value="-vpr">VPR</option>
          <option value="name">Name</option>
        </Select>
        <Button
          aria-pressed={exploitable}
          onClick={() => setExploitable((v) => !v)}
          className={cn(exploitable && "border-critical/40 bg-critical/8 text-critical")}
        >
          <Flame className="size-3.5" /> Exploitable
        </Button>
      </div>
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : !data?.items.length ? (
          <EmptyState icon={<Bug className="size-8" />} title="No open vulnerabilities match" />
        ) : (
          <div className={cn("overflow-x-auto", isFetching && "opacity-70")}>
            <table className="w-full text-sm">
              <thead className="bg-surface-2/60 text-left text-xs text-ink-3">
                <tr>
                  <th className="px-4 py-2 font-medium">Severity</th>
                  <th className="px-4 py-2 font-medium">Vulnerability</th>
                  <th className="px-4 py-2 font-medium">CVEs</th>
                  <th className="px-4 py-2 text-right font-medium">CVSS</th>
                  <th className="px-4 py-2 text-right font-medium">VPR</th>
                  <th className="px-4 py-2 text-right font-medium">Hosts</th>
                  <th className="px-4 py-2 text-right font-medium">Instances</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.items.map((v) => (
                  <tr key={v.plugin_id} className="hover:bg-surface-2/60">
                    <td className="px-4 py-2">
                      <SeverityBadge severity={v.severity} />
                    </td>
                    <td className="max-w-lg px-4 py-2">
                      <Link
                        to="/vulnerabilities/$pluginId"
                        params={{ pluginId: String(v.plugin_id) }}
                        className="flex items-center gap-1.5 hover:text-brand"
                      >
                        {v.exploit_available && (
                          <Flame className="size-3.5 shrink-0 text-critical" aria-label="Exploit available" />
                        )}
                        <span className="truncate">{v.name}</span>
                      </Link>
                      <div className="font-mono text-[11px] text-ink-3">
                        {v.plugin_id} · {v.family}
                      </div>
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-ink-2">
                      {v.cves[0] ?? "—"}
                      {v.cves.length > 1 && <span className="text-ink-3"> +{v.cves.length - 1}</span>}
                    </td>
                    <td className="num px-4 py-2 text-right font-mono text-xs">{v.cvss3_base ?? "—"}</td>
                    <td className="num px-4 py-2 text-right font-mono text-xs">{v.vpr_score ?? "—"}</td>
                    <td className="num px-4 py-2 text-right font-mono">
                      <Link
                        to="/findings"
                        search={{ plugin_id: [v.plugin_id], group: "host" }}
                        className="hover:text-brand"
                      >
                        {fmtNum(v.hosts)}
                      </Link>
                    </td>
                    <td className="num px-4 py-2 text-right font-mono text-ink-2">{fmtNum(v.instances)}</td>
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
