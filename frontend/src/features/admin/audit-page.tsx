import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card, Input, PageHeader, Pagination, Select } from "@/components/ui/primitives";
import { api } from "@/lib/api";
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
];

export function AuditPage() {
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const dActor = useDebounced(actor);
  const { data } = useQuery({
    queryKey: ["audit", dActor, action, page],
    queryFn: () => api.get<Page<AuditEntry>>("/audit", { actor: dActor, action, page, page_size: 50 }),
    placeholderData: keepPreviousData,
  });

  return (
    <div className="animate-in">
      <PageHeader
        title="Audit log"
        description="Append-only record of sign-ins, imports, status changes, exports and administrative actions."
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
                        /failed|locked|reuse|deleted/.test(e.action)
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
