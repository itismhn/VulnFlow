import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { BadgeCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { SeverityBadge } from "@/components/severity";
import { Dialog } from "@/components/ui/overlay";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  PageHeader,
  Pagination,
  Skeleton,
  Textarea,
} from "@/components/ui/primitives";
import { FindingDrawer } from "@/features/findings/finding-drawer";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AcceptanceStatus, Page, RiskAcceptanceRow } from "@/lib/types";
import { cn, fmtDate, fmtRelative } from "@/lib/utils";
import { useAppSettings } from "./risk-dialog";

const TABS: { key: string; label: string; status: AcceptanceStatus[] }[] = [
  { key: "pending", label: "Pending", status: ["pending"] },
  { key: "approved", label: "Active", status: ["approved"] },
  { key: "closed", label: "Closed", status: ["rejected", "expired", "revoked"] },
];

const TONE = {
  pending: "warn",
  approved: "brand",
  rejected: "danger",
  expired: "neutral",
  revoked: "neutral",
} as const;

const PAGE_SIZE = 25;

export function ApprovalsPage({ finding }: { finding?: number }) {
  const { can, me } = useAuth();
  const navigate = useNavigate({ from: "/approvals" });
  const qc = useQueryClient();
  const [tab, setTab] = useState("pending");
  const [page, setPage] = useState(1);
  const [deciding, setDeciding] = useState<{ row: RiskAcceptanceRow; approve: boolean } | null>(null);
  const [note, setNote] = useState("");
  const { data: settings } = useAppSettings();
  const current = TABS.find((t) => t.key === tab) ?? TABS[0];

  const { data, isLoading } = useQuery({
    queryKey: ["risk", "list", tab, page],
    queryFn: () =>
      api.get<Page<RiskAcceptanceRow>>("/risk-acceptances", {
        status: current.status,
        page,
        page_size: PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["risk"] });
    qc.invalidateQueries({ queryKey: ["findings"] });
    qc.invalidateQueries({ queryKey: ["finding"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: number; approve: boolean }) =>
      api.post(`/risk-acceptances/${id}/decision`, { approve, note }),
    onSuccess: (_, v) => {
      toast.success(v.approve ? "Risk accepted" : "Request rejected");
      setDeciding(null);
      setNote("");
      refresh();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const revoke = useMutation({
    mutationFn: (id: number) => api.post(`/risk-acceptances/${id}/revoke`, { note: "" }),
    onSuccess: () => {
      toast.success("Acceptance revoked; the finding is open again");
      refresh();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const approver = can("risk:approve");
  const selfBlocked = (r: RiskAcceptanceRow) =>
    r.requested_by?.id === me?.id && !settings?.risk_self_approval;

  return (
    <div className="animate-in">
      <PageHeader
        title="Risk approvals"
        description={
          approver
            ? "Review requests to accept risk. Approved findings leave the open backlog until the expiry date, then reopen automatically."
            : "Requests to accept risk and their decisions. Approval is done by an administrator."
        }
      />
      <div className="mb-3 flex gap-1 text-sm" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => {
              setTab(t.key);
              setPage(1);
            }}
            className={cn(
              "rounded-md px-3 py-1.5 font-medium transition",
              tab === t.key ? "bg-brand-soft text-brand" : "text-ink-2 hover:bg-surface-2",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        ) : !data?.items.length ? (
          <EmptyState
            icon={<BadgeCheck className="size-8" />}
            title={`No ${current.label.toLowerCase()} requests`}
          >
            {tab === "pending"
              ? "Analysts request acceptance from a finding's detail panel or with a bulk selection."
              : "Nothing here yet."}
          </EmptyState>
        ) : (
          <ul className="divide-y divide-line">
            {data.items.map((r) => (
              <li key={r.id} className="grid gap-3 px-4 py-3.5 md:grid-cols-[1fr_auto]">
                <div className="min-w-0 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={r.finding.severity} />
                    <button
                      type="button"
                      onClick={() => navigate({ search: { finding: r.finding_id } })}
                      className="min-w-0 truncate text-left text-sm font-medium hover:text-brand"
                    >
                      {r.finding.plugin.name}
                    </button>
                    <span className="font-mono text-xs text-ink-3">
                      {r.finding.asset.ip}:{r.finding.port}
                    </span>
                    <Badge tone={TONE[r.status]}>{r.status}</Badge>
                  </div>
                  <p className="text-sm whitespace-pre-line text-ink-2">{r.justification}</p>
                  <div className="text-xs text-ink-3">
                    Requested by {r.requested_by?.username ?? "unknown"} {fmtRelative(r.created_at)} · accept
                    until <span className="text-ink-2">{fmtDate(r.expires_at)}</span>
                    {r.decided_by && (
                      <>
                        {" "}
                        · {r.status === "approved" ? "approved" : r.status} by {r.decided_by.username}{" "}
                        {fmtRelative(r.decided_at)}
                      </>
                    )}
                    {r.decision_note && <> · “{r.decision_note}”</>}
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  {r.status === "pending" && approver && (
                    <>
                      {selfBlocked(r) && (
                        <span className="self-center text-xs text-ink-3">Needs a second admin</span>
                      )}
                      <Button size="sm" onClick={() => setDeciding({ row: r, approve: false })}>
                        Reject
                      </Button>
                      <Button
                        size="sm"
                        variant="primary"
                        disabled={selfBlocked(r)}
                        onClick={() => setDeciding({ row: r, approve: true })}
                      >
                        Approve
                      </Button>
                    </>
                  )}
                  {r.status === "pending" && !approver && r.requested_by?.id === me?.id && (
                    <Button size="sm" variant="ghost" onClick={() => revoke.mutate(r.id)}>
                      Withdraw
                    </Button>
                  )}
                  {r.status === "approved" && approver && (
                    <Button size="sm" variant="ghost" onClick={() => revoke.mutate(r.id)}>
                      Revoke
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        {data && data.total > PAGE_SIZE && (
          <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
        )}
      </Card>

      <Dialog
        open={!!deciding}
        onOpenChange={(o) => !o && setDeciding(null)}
        title={deciding?.approve ? "Approve risk acceptance" : "Reject request"}
        description={
          deciding &&
          `${deciding.row.finding.plugin.name} on ${deciding.row.finding.asset.ip}, until ${fmtDate(deciding.row.expires_at)}`
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeciding(null)}>
              Cancel
            </Button>
            <Button
              variant={deciding?.approve ? "primary" : "danger"}
              loading={decide.isPending}
              disabled={!deciding?.approve && !note.trim()}
              onClick={() => deciding && decide.mutate({ id: deciding.row.id, approve: deciding.approve })}
            >
              {deciding?.approve ? "Approve" : "Reject"}
            </Button>
          </>
        }
      >
        <Field
          label={deciding?.approve ? "Note (optional)" : "Reason for rejecting"}
          hint="Recorded on the finding's history and sent to the requester."
        >
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </Dialog>

      <FindingDrawer id={finding} onClose={() => navigate({ search: {} })} />
    </div>
  );
}
