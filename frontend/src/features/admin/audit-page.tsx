import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { Button, Card, Input, PageHeader, Pagination, Select } from "@/components/ui/primitives";
import { api, downloadUrl } from "@/lib/api";
import { useDebounced } from "@/lib/hooks";
import type { AuditEntry, Page } from "@/lib/types";
import { cn, fmtDate } from "@/lib/utils";

const ACTION_GROUPS = [
  "auth",
  "user",
  "scan",
  "finding",
  "findings",
  "network",
  "report",
  "template",
  "asset",
  "risk",
  "suppression",
  "sla_policy",
  "settings",
  "audit",
];

export function AuditPage() {
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [page, setPage] = useState(1);
  const dActor = useDebounced(actor);
  // Dates are inclusive days in the browser's timezone
  const range = {
    since: since ? new Date(`${since}T00:00:00`).toISOString() : undefined,
    until: until ? new Date(new Date(`${until}T00:00:00`).getTime() + 86_400_000).toISOString() : undefined,
  };
  const query = { actor: dActor, action, ...range };
  const { data } = useQuery({
    queryKey: ["audit", query, page],
    queryFn: () => api.get<Page<AuditEntry>>("/audit", { ...query, page, page_size: 50 }),
    placeholderData: keepPreviousData,
  });

  return (
    <div className="animate-in">
      <PageHeader
        title="Audit log"
        description="Append-only record of sign-ins, imports, status changes, exports and administrative actions."
        actions={
          <Button onClick={() => window.location.assign(downloadUrl("/audit/export", query))}>
            <Download className="size-4" /> Export CSV
          </Button>
        }
      />
      <div className="mb-3 flex flex-wrap gap-2">
        <Input
          value={actor}
          onChange={(e) => {
            setActor(e.target.value);
            setPage(1);
          }}
          placeholder="Filter by user"
          className="w-56"
        />
        <Select
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setPage(1);
          }}
          className="w-48"
        >
          <option value="">All actions</option>
          {ACTION_GROUPS.map((a) => (
            <option key={a} value={`${a}.`}>
              {a}.*
            </option>
          ))}
        </Select>
        <Input
          type="date"
          value={since}
          max={until || undefined}
          onChange={(e) => {
            setSince(e.target.value);
            setPage(1);
          }}
          className="w-40"
          aria-label="From date"
        />
        <Input
          type="date"
          value={until}
          min={since || undefined}
          onChange={(e) => {
            setUntil(e.target.value);
            setPage(1);
          }}
          className="w-40"
          aria-label="To date"
        />
      </div>
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface-2/60 text-left text-xs text-ink-3">
              <tr>
                <th className="px-4 py-2 font-medium">Time</th>
                <th className="px-4 py-2 font-medium">User</th>
                <th className="px-4 py-2 font-medium">Action</th>
                <th className="px-4 py-2 font-medium">Target</th>
                <th className="px-4 py-2 font-medium">Details</th>
                <th className="px-4 py-2 font-medium">Source IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data?.items.map((e) => (
                <tr key={e.id}>
                  <td className="px-4 py-2 text-xs whitespace-nowrap text-ink-2">
                    {fmtDate(e.created_at, true)}
                  </td>
                  <td className="px-4 py-2">{e.actor_username}</td>
                  <td className="px-4 py-2">
                    <span
                      className={cn(
                        "rounded px-1.5 py-0.5 font-mono text-xs",
                        /failed|locked|reuse|deleted|revoked|purged/.test(e.action)
                          ? "bg-critical/10 text-critical"
                          : "bg-surface-2 text-ink-2",
                      )}
                    >
                      {e.action}
                    </span>
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-ink-2">
                    {e.entity_type ? `${e.entity_type}#${e.entity_id}` : "—"}
                  </td>
                  <td
                    className="max-w-md truncate px-4 py-2 font-mono text-[11px] text-ink-3"
                    title={JSON.stringify(e.details)}
                  >
                    {Object.keys(e.details).length ? JSON.stringify(e.details) : ""}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-ink-3">{e.ip}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data && <Pagination page={page} pageSize={50} total={data.total} onChange={setPage} />}
      </Card>
    </div>
  );
}
