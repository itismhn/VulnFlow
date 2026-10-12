import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  Archive,
  Download,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { SeverityCounters, SeverityStrip } from "@/components/severity";
import { NotFound } from "@/components/states";
import { Dialog, DropdownMenu, MenuItem, MenuSeparator, Tooltip } from "@/components/ui/overlay";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  PageHeader,
  Skeleton,
  Textarea,
} from "@/components/ui/primitives";
import { api, downloadUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Scan, ScanDiff, ScanHost } from "@/lib/types";
import { fmtBytes, fmtDate, fmtNum, scanCounts } from "@/lib/utils";
import { ScanStatusBadge } from "./scans-page";

export function ScanDetailPage({ id }: { id: number }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const { data: scan, isError } = useQuery({
    queryKey: ["scans", "detail", id],
    queryFn: () => api.get<Scan>(`/scans/${id}`),
    refetchInterval: (q) =>
      q.state.data && ["queued", "parsing"].includes(q.state.data.status) ? 1500 : false,
  });
  const done = scan?.status === "done";
  const { data: hosts } = useQuery({
    queryKey: ["scans", "hosts", id],
    queryFn: () => api.get<ScanHost[]>(`/scans/${id}/hosts`),
    enabled: done,
  });
  const { data: previous } = useQuery({
    queryKey: ["scans", "previous", id],
    queryFn: () => api.get<Scan | null>(`/scans/${id}/previous`),
    enabled: done,
  });
  const { data: diff } = useQuery({
    queryKey: ["scans", "diff", id, previous?.id],
    queryFn: () => api.get<ScanDiff>(`/scans/${id}/diff`, { against: previous?.id }),
    enabled: !!previous,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["scans"] });
    qc.invalidateQueries({ queryKey: ["findings"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const update = useMutation({
    mutationFn: (body: Partial<Pick<Scan, "name" | "notes" | "archived">>) =>
      api.patch<Scan>(`/scans/${id}`, body),
    onSuccess: () => {
      invalidate();
      setEditing(false);
      toast.success("Scan updated");
    },
  });
  const reparse = useMutation({
    mutationFn: () => api.post<Scan>(`/scans/${id}/reparse`),
    onSuccess: () => {
      invalidate();
      toast.success("Re-import started");
    },
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/scans/${id}`),
    onSuccess: () => {
      invalidate();
      toast.success("Scan deleted");
      navigate({ to: "/scans" });
    },
  });

  if (isError) return <NotFound what="Scan" />;
  if (!scan) return <Skeleton className="h-64" />;
  const counts = scanCounts(scan);
  const credentialed = hosts?.filter((h) => h.credentialed).length ?? 0;

  return (
    <div className="animate-in">
      <PageHeader
        eyebrow={
          <Link to="/scans" className="hover:text-ink">
            Scan history
          </Link>
        }
        title={
          <span className="flex flex-wrap items-center gap-2">
            {scan.name}
            <ScanStatusBadge scan={scan} />
            {scan.archived && <Badge>Archived</Badge>}
          </span>
        }
        description={
          <>
            {scan.policy_name || "Unknown policy"} · scanned {fmtDate(scan.started_at, true)} ·{" "}
            {fmtBytes(scan.size_bytes)} · imported by {scan.uploaded_by?.username ?? "—"}
          </>
        }
        actions={
          <>
            {done && (
              <Link to="/findings" search={{ scan_id: id }}>
                <Button variant="primary">Findings in this scan</Button>
              </Link>
            )}
            {can("scans:upload") && (
              <DropdownMenu
                trigger={
                  <Button size="icon" aria-label="More actions">
                    <MoreHorizontal className="size-4" />
                  </Button>
                }
              >
                <MenuItem onSelect={() => setEditing(true)}>
                  <Pencil className="size-4" /> Rename or add notes
                </MenuItem>
                <MenuItem onSelect={() => update.mutate({ archived: !scan.archived })}>
                  <Archive className="size-4" /> {scan.archived ? "Unarchive" : "Archive"}
                </MenuItem>
                {can("scans:manage") && (
                  <>
                    <MenuItem onSelect={() => reparse.mutate()}>
                      <RefreshCw className="size-4" /> Re-import file
                    </MenuItem>
                    <MenuItem onSelect={() => window.location.assign(downloadUrl(`/scans/${id}/download`))}>
                      <Download className="size-4" /> Download original .nessus
                    </MenuItem>
                    <MenuSeparator />
                    <MenuItem danger onSelect={() => setConfirmDelete(true)}>
                      <Trash2 className="size-4" /> Delete scan
                    </MenuItem>
                  </>
                )}
              </DropdownMenu>
            )}
          </>
        }
      />

      {scan.status === "failed" && (
        <Card className="mb-4 border-critical/30 bg-critical/5 p-4 text-sm text-critical">{scan.error}</Card>
      )}
      {(scan.status === "queued" || scan.status === "parsing") && (
        <Card className="mb-4 p-4">
          <div className="mb-2 text-sm">Importing… large files can take a few minutes.</div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-2">
            <div className="h-full bg-brand transition-all" style={{ width: `${scan.progress}%` }} />
          </div>
        </Card>
      )}

      {done && (
        <>
          <div className="mb-4 grid gap-4 md:grid-cols-3">
            <Card className="p-4">
              <div className="text-xs text-ink-3">Coverage</div>
              <div className="num mt-1 font-display text-3xl font-semibold">
                {fmtNum(scan.host_count)} hosts
              </div>
              <div className="mt-1 text-xs text-ink-2">
                {credentialed} credentialed · {scan.host_count - credentialed} uncredentialed
                {scan.skipped_hosts > 0 && ` · ${scan.skipped_hosts} skipped (no IP)`}
              </div>
            </Card>
            <Card className="p-4">
              <div className="text-xs text-ink-3">Findings in this scan</div>
              <div className="num mt-1 font-display text-3xl font-semibold">{fmtNum(scan.finding_count)}</div>
              <SeverityStrip counts={counts} className="mt-2" />
              <SeverityCounters counts={counts} className="mt-2" />
            </Card>
            <Card className="p-4">
              <div className="text-xs text-ink-3">
                {previous ? (
                  <>
                    Compared with{" "}
                    <Link
                      to="/scans/$scanId"
                      params={{ scanId: String(previous.id) }}
                      className="text-brand hover:underline"
                    >
                      {previous.name}
                    </Link>
                  </>
                ) : (
                  "Lifecycle changes"
                )}
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-center">
                <Delta label="New" value={diff?.new ?? scan.new_count} tone="text-critical" />
                <Delta label="Fixed" value={diff?.fixed ?? scan.fixed_count} tone="text-ok" />
                <Delta
                  label={diff ? "Persisting" : "Reopened"}
                  value={diff?.persisting ?? scan.reopened_count}
                  tone="text-ink"
                />
              </div>
              {!previous ? (
                <p className="mt-2 text-xs text-ink-3">No earlier scan of these hosts to compare with.</p>
              ) : (
                <Link
                  to="/scans/compare"
                  search={{ base: previous.id, compare: scan.id }}
                  className="mt-2 inline-block text-xs text-brand hover:underline"
                >
                  See the findings in each group →
                </Link>
              )}
            </Card>
          </div>

          {scan.notes && (
            <Card className="mb-4 p-4 text-sm whitespace-pre-line text-ink-2">{scan.notes}</Card>
          )}

          <Card className="overflow-hidden">
            <CardHeader title="Hosts in this scan" description="Ordered by most critical findings" />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-surface-2/60 text-left text-xs text-ink-3">
                  <tr>
                    <th className="px-4 py-2 font-medium">Host</th>
                    <th className="px-4 py-2 font-medium">Operating system</th>
                    <th className="px-4 py-2 font-medium">Auth</th>
                    <th className="w-40 px-4 py-2 font-medium">Severity mix</th>
                    <th className="px-4 py-2 font-medium">Counts (C/H/M/L)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {hosts?.map((h) => (
                    <tr key={h.asset_id} className="hover:bg-surface-2/60">
                      <td className="px-4 py-2">
                        <Link
                          to="/assets/$assetId"
                          params={{ assetId: String(h.asset_id) }}
                          className="font-mono hover:text-brand"
                        >
                          {h.ip}
                        </Link>
                        <div className="text-xs text-ink-3">{h.hostname}</div>
                      </td>
                      <td className="max-w-xs truncate px-4 py-2 text-xs text-ink-2">{h.os || "—"}</td>
                      <td className="px-4 py-2">
                        {h.credentialed ? (
                          <Tooltip content="Credentialed scan: local checks ran">
                            <ShieldCheck className="size-4 text-ok" />
                          </Tooltip>
                        ) : (
                          <Tooltip content="Uncredentialed: network checks only. Findings from earlier credentialed scans are not auto-closed.">
                            <ShieldOff className="size-4 text-ink-3" />
                          </Tooltip>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        <SeverityStrip counts={h.counts} />
                      </td>
                      <td className="px-4 py-2">
                        <SeverityCounters counts={h.counts} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <EditScanDialog
        key={`${scan.name}-${editing}`}
        open={editing}
        onOpenChange={setEditing}
        scan={scan}
        saving={update.isPending}
        onSave={(body) => update.mutate(body)}
      />
      <Dialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this scan?"
        description="This can't be undone."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              Delete scan
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink-2">
          Its findings history is removed, findings seen only in this scan are deleted, and status changes it
          caused (auto-fixed or reopened) are reverted. Consider archiving instead to keep the history.
        </p>
      </Dialog>
    </div>
  );
}

function Delta({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div>
      <div className={`num font-display text-2xl font-semibold ${value ? tone : "text-ink-3"}`}>
        {fmtNum(value)}
      </div>
      <div className="text-[11px] text-ink-3">{label}</div>
    </div>
  );
}

function EditScanDialog({
  open,
  onOpenChange,
  scan,
  saving,
  onSave,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  scan: Scan;
  saving: boolean;
  onSave: (body: { name: string; notes: string }) => void;
}) {
  const [name, setName] = useState(scan.name);
  const [notes, setNotes] = useState(scan.notes);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Edit scan"
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" loading={saving} onClick={() => onSave({ name, notes })}>
            Save changes
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Notes" hint="Scope, exclusions, or anything the next analyst should know.">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </div>
    </Dialog>
  );
}
