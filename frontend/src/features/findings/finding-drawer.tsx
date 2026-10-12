import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ExternalLink, EyeOff, Flame, SearchX, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { SeverityBadge, StatusBadge } from "@/components/severity";
import { Drawer } from "@/components/ui/overlay";
import {
  Badge,
  Button,
  EmptyState,
  Field,
  Input,
  Select,
  Skeleton,
  Textarea,
} from "@/components/ui/primitives";
import { DueDate } from "@/features/workflow/due-date";
import { RiskRequestDialog } from "@/features/workflow/risk-dialog";
import { SuppressDialog } from "@/features/workflow/suppress-dialog";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useDirectory } from "@/lib/queries";
import type { FindingDetail, FindingStatus, RiskAcceptance } from "@/lib/types";
import {
  ACTIVE_STATUSES,
  cn,
  daysSince,
  fmtDate,
  fmtRelative,
  STATUS_LABELS,
  severityLabel,
} from "@/lib/utils";

export function FindingDrawer({ id, onClose }: { id: number | undefined; onClose: () => void }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["finding", id],
    queryFn: () => api.get<FindingDetail>(`/findings/${id}`),
    enabled: !!id,
  });
  const [tab, setTab] = useState<"overview" | "output" | "history">("overview");

  return (
    <Drawer open={!!id} onOpenChange={(o) => !o && onClose()} title={data ? data.plugin.name : "Finding"}>
      {isError ? (
        <EmptyState icon={<SearchX className="size-6" />} title="Finding not found">
          It may have been deleted, or it is outside the networks you have access to.
        </EmptyState>
      ) : isLoading || !data ? (
        <div className="space-y-3 p-5">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-24" />
          <Skeleton className="h-40" />
        </div>
      ) : (
        <div>
          <div className="space-y-3 border-b border-line px-5 py-4">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={data.severity} />
              <StatusBadge status={data.status} />
              {data.plugin.exploit_available && (
                <Badge tone="danger">
                  <Flame className="size-3" /> Exploit available
                </Badge>
              )}
              {data.reopen_count > 0 && <Badge tone="warn">Reopened {data.reopen_count}×</Badge>}
              <DueDate
                date={data.due_date}
                source={data.due_source}
                active={ACTIVE_STATUSES.includes(data.status)}
                className="ml-auto"
              />
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
              <Fact label="Host">
                <Link
                  to="/assets/$assetId"
                  params={{ assetId: String(data.asset.id) }}
                  className="font-mono text-brand hover:underline"
                >
                  {data.asset.ip}
                </Link>
                <div className="truncate text-xs text-ink-3">{data.asset.hostname || data.asset.fqdn}</div>
              </Fact>
              <Fact label="Port">
                <span className="font-mono">
                  {data.port}/{data.protocol}
                </span>
                <div className="text-xs text-ink-3">{data.service}</div>
              </Fact>
              <Fact label="First seen">
                {fmtDate(data.first_seen)}
                <div className="text-xs text-ink-3">{daysSince(data.first_seen)} days open</div>
              </Fact>
              <Fact label="Last seen">
                {fmtDate(data.last_seen)}
                <div className="text-xs text-ink-3">{fmtRelative(data.last_seen)}</div>
              </Fact>
            </dl>
          </div>

          <FindingActions
            key={`${data.id}-${data.status}-${data.assignee?.id}-${data.due_date}`}
            finding={data}
          />
          <RiskPanel finding={data} />

          <div className="flex gap-1 border-b border-line px-5" role="tablist">
            {(
              [
                ["overview", "Overview"],
                ["output", "Plugin output"],
                ["history", `History (${data.events.length})`],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className={cn(
                  "-mb-px border-b-2 px-3 py-2 text-sm transition",
                  tab === key
                    ? "border-brand font-medium text-ink"
                    : "border-transparent text-ink-3 hover:text-ink",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="px-5 py-4">
            {tab === "overview" && <Overview finding={data} />}
            {tab === "output" && (
              <pre className="overflow-x-auto rounded-md bg-surface-2 p-3 font-mono text-xs whitespace-pre-wrap">
                {data.plugin_output || "No output recorded for this finding."}
              </pre>
            )}
            {tab === "history" && <History finding={data} />}
          </div>
        </div>
      )}
    </Drawer>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-ink-3">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  );
}

function Overview({ finding: f }: { finding: FindingDetail }) {
  const p = f.plugin;
  return (
    <div className="space-y-5 text-sm leading-relaxed">
      {p.synopsis && <p className="text-ink-2">{p.synopsis}</p>}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Score label="CVSS v3" value={p.cvss3_base} />
        <Score label="CVSS v2" value={p.cvss2_base} />
        <Score label="VPR" value={p.vpr_score} />
        <Score label="EPSS" value={p.epss_score} />
      </div>
      <Section title="Description">{p.description}</Section>
      <Section title="Solution">
        <div className="rounded-md border border-ok/25 bg-ok/6 p-3">
          {p.solution || "No solution provided."}
        </div>
      </Section>
      {p.cves.length > 0 && (
        <Section title={`CVEs (${p.cves.length})`}>
          <div className="flex flex-wrap gap-1.5">
            {p.cves.map((c) => (
              <Link
                key={c}
                to="/findings"
                search={{ cve: c }}
                className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs hover:text-brand"
              >
                {c}
              </Link>
            ))}
          </div>
        </Section>
      )}
      {p.see_also.length > 0 && (
        <Section title="References">
          <ul className="space-y-1">
            {p.see_also.map((url) => (
              <li key={url}>
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1 break-all text-brand hover:underline"
                >
                  {url} <ExternalLink className="size-3 shrink-0" />
                </a>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <Section title="Plugin">
        <p className="text-ink-2">
          <Link
            to="/vulnerabilities/$pluginId"
            params={{ pluginId: String(p.id) }}
            className="font-mono text-brand hover:underline"
          >
            {p.id}
          </Link>{" "}
          · {p.family}
          {p.exploit_frameworks.length > 0 && <> · Exploit frameworks: {p.exploit_frameworks.join(", ")}</>}
          {p.patch_publication_date && <> · Patch published {fmtDate(p.patch_publication_date)}</>}
        </p>
      </Section>
    </div>
  );
}

function Score({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-md border border-line px-3 py-2">
      <div className="text-[11px] text-ink-3">{label}</div>
      <div className="num font-mono text-lg">{value ?? "—"}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className="mb-1.5 font-display text-sm font-semibold">{title}</h4>
      <div className="whitespace-pre-line text-ink-2">{children}</div>
    </section>
  );
}

function History({ finding: f }: { finding: FindingDetail }) {
  return (
    <div className="space-y-6">
      <ol className="relative space-y-4 border-l border-line pl-5">
        {f.events.map((e) => (
          <li key={e.id} className="relative">
            <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-surface bg-ink-3" />
            <div className="text-sm">
              {e.kind === "status" || e.kind === "detected" ? (
                e.from_status ? (
                  <>
                    {STATUS_LABELS[e.from_status as FindingStatus]} →{" "}
                    <strong>{STATUS_LABELS[e.to_status as FindingStatus]}</strong>
                  </>
                ) : (
                  <strong>First detected</strong>
                )
              ) : e.kind === "assign" ? (
                <strong>{e.note.split(":")[0]}</strong>
              ) : e.kind === "risk" ? (
                <strong>Risk acceptance</strong>
              ) : (
                <strong>Comment</strong>
              )}
              {e.note && e.kind !== "assign" && e.kind !== "detected" && (
                <p className="mt-0.5 text-ink-2">{e.note}</p>
              )}
            </div>
            <div className="mt-0.5 text-xs text-ink-3">
              {e.actor ? e.actor.username : e.scan_id ? `Scan #${e.scan_id}` : "System"} ·{" "}
              {fmtDate(e.created_at, true)}
            </div>
          </li>
        ))}
      </ol>
      <div>
        <h4 className="mb-2 font-display text-sm font-semibold">Seen in scans</h4>
        <ul className="divide-y divide-line rounded-md border border-line text-sm">
          {f.occurrences.map((o) => (
            <li key={o.scan_id} className="flex items-center justify-between gap-3 px-3 py-2">
              <Link
                to="/scans/$scanId"
                params={{ scanId: String(o.scan_id) }}
                className="truncate hover:text-brand"
              >
                {o.scan_name}
              </Link>
              <span className="shrink-0 text-xs text-ink-3">
                {severityLabel(o.severity)} · {fmtDate(o.observed_at)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function FindingActions({ finding: f }: { finding: FindingDetail }) {
  const { can, me } = useAuth();
  const qc = useQueryClient();
  const { data: users = [] } = useDirectory(can("findings:update"));
  const [riskOpen, setRiskOpen] = useState(false);
  const [suppressOpen, setSuppressOpen] = useState(false);
  const { data: acceptances = [] } = useQuery({
    queryKey: ["risk", "finding", f.id],
    queryFn: () => api.get<RiskAcceptance[]>(`/risk-acceptances/finding/${f.id}`),
  });
  const riskOpenRequest = acceptances.some((r) => r.status === "pending" || r.status === "approved");
  const [status, setStatus] = useState<FindingStatus>(f.status);
  const [note, setNote] = useState("");
  const [assignee, setAssignee] = useState(f.assignee?.id ?? 0);
  const [due, setDue] = useState(f.due_date ?? "");

  const save = useMutation({
    mutationFn: () =>
      api.patch(`/findings/${f.id}`, {
        status: status !== f.status ? status : undefined,
        assignee_id: assignee && assignee !== f.assignee?.id ? assignee : undefined,
        clear_assignee: !assignee && !!f.assignee,
        due_date: due && due !== f.due_date ? due : undefined,
        note,
      }),
    onError: (e: Error) => toast.error(e.message),
    onSuccess: () => {
      toast.success("Finding updated");
      setNote("");
      qc.invalidateQueries({ queryKey: ["finding", f.id] });
      qc.invalidateQueries({ queryKey: ["findings"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const resetDue = useMutation({
    mutationFn: () => api.patch(`/findings/${f.id}`, { clear_due_date: true }),
    onSuccess: () => {
      toast.success("Due date follows the SLA policy again");
      qc.invalidateQueries({ queryKey: ["finding", f.id] });
      qc.invalidateQueries({ queryKey: ["findings"] });
    },
  });

  if (!can("findings:update")) return null;
  const needsNote = status === "false_positive" && status !== f.status;
  const dirty =
    status !== f.status || assignee !== (f.assignee?.id ?? 0) || due !== (f.due_date ?? "") || note.trim();
  // Risk acceptance goes through the request/approval flow, not the status picker
  const statusOptions = (Object.keys(STATUS_LABELS) as FindingStatus[]).filter(
    (s) => s !== "risk_accepted" || f.status === "risk_accepted",
  );

  return (
    <div className="space-y-3 border-b border-line bg-surface-2/50 px-5 py-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Status">
          <Select value={status} onChange={(e) => setStatus(e.target.value as FindingStatus)}>
            {statusOptions.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Assignee">
          <Select value={assignee} onChange={(e) => setAssignee(Number(e.target.value))}>
            <option value={0}>Unassigned</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name || u.username}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="Due date"
          hint={
            f.due_source === "manual" ? (
              <button type="button" className="text-brand hover:underline" onClick={() => resetDue.mutate()}>
                Reset to SLA policy
              </button>
            ) : f.due_source === "sla" ? (
              "Set by SLA policy"
            ) : undefined
          }
        >
          <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
        </Field>
      </div>
      <Field
        label={needsNote ? "Reason (required)" : "Comment"}
        error={needsNote && !note.trim() ? "Explain why, for the audit trail" : null}
      >
        <Textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={
            needsNote
              ? "Why is this a false positive?"
              : "Add a note for the team. Type @username to notify someone."
          }
          className="min-h-16"
        />
      </Field>
      <div className="flex flex-wrap items-center justify-end gap-2">
        {can("risk:request") && ACTIVE_STATUSES.includes(f.status) && !riskOpenRequest && (
          <Button size="sm" variant="ghost" onClick={() => setRiskOpen(true)}>
            <ShieldCheck className="size-3.5" /> Request risk acceptance
          </Button>
        )}
        {!me?.scope_restricted && (
          <Button size="sm" variant="ghost" onClick={() => setSuppressOpen(true)}>
            <EyeOff className="size-3.5" /> False positive on all hosts
          </Button>
        )}
        <Button
          variant="primary"
          size="sm"
          className="ml-auto"
          disabled={!dirty || (needsNote && !note.trim())}
          loading={save.isPending}
          onClick={() => save.mutate()}
        >
          Save changes
        </Button>
      </div>
      <RiskRequestDialog findingIds={[f.id]} open={riskOpen} onOpenChange={setRiskOpen} />
      <SuppressDialog plugin={f.plugin} open={suppressOpen} onOpenChange={setSuppressOpen} />
    </div>
  );
}

const RISK_TONE = {
  pending: "warn",
  approved: "brand",
  rejected: "danger",
  expired: "neutral",
  revoked: "neutral",
} as const;

function RiskPanel({ finding: f }: { finding: FindingDetail }) {
  const { can, me } = useAuth();
  const qc = useQueryClient();
  const { data = [] } = useQuery({
    queryKey: ["risk", "finding", f.id],
    queryFn: () => api.get<RiskAcceptance[]>(`/risk-acceptances/finding/${f.id}`),
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["risk"] });
    qc.invalidateQueries({ queryKey: ["finding", f.id] });
    qc.invalidateQueries({ queryKey: ["findings"] });
  };
  const revoke = useMutation({
    mutationFn: (id: number) => api.post(`/risk-acceptances/${id}/revoke`, { note: "" }),
    onSuccess: () => {
      toast.success("Risk acceptance withdrawn");
      refresh();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const current = data.find((r) => r.status === "pending" || r.status === "approved");
  if (!current) return null;
  const canRevoke =
    current.status === "approved"
      ? can("risk:approve")
      : current.requested_by?.id === me?.id || can("risk:approve");
  return (
    <div className="flex items-start gap-3 border-b border-line px-5 py-3 text-sm">
      <ShieldCheck className="mt-0.5 size-4 shrink-0 text-medium" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={RISK_TONE[current.status]}>
            {current.status === "pending" ? "Awaiting approval" : "Risk accepted"}
          </Badge>
          <span className="text-xs text-ink-3">
            until {fmtDate(current.expires_at)} · requested by {current.requested_by?.username ?? "unknown"}
            {current.decided_by && ` · approved by ${current.decided_by.username}`}
          </span>
        </div>
        <p className="mt-1 text-ink-2">{current.justification}</p>
      </div>
      {canRevoke && (
        <Button
          size="sm"
          variant="ghost"
          loading={revoke.isPending}
          onClick={() => revoke.mutate(current.id)}
        >
          {current.status === "pending" ? "Withdraw" : "Revoke"}
        </Button>
      )}
    </div>
  );
}
