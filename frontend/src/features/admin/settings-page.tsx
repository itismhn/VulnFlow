import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Field,
  Input,
  PageHeader,
  Select,
} from "@/components/ui/primitives";
import { useAppSettings } from "@/features/workflow/risk-dialog";
import { api } from "@/lib/api";
import { useZones } from "@/lib/queries";
import type { AppSettings, SlaPolicy, SuppressionRule } from "@/lib/types";
import { cn, fmtDate } from "@/lib/utils";

const SEVS = [
  { key: "critical_days", label: "Critical", cls: "bg-critical" },
  { key: "high_days", label: "High", cls: "bg-high" },
  { key: "medium_days", label: "Medium", cls: "bg-medium" },
  { key: "low_days", label: "Low", cls: "bg-low" },
] as const;

type PolicyDraft = Omit<SlaPolicy, "id" | "updated_at"> & { id?: number };

export function SettingsPage() {
  return (
    <div className="animate-in space-y-5">
      <PageHeader
        title="Settings"
        description="Remediation deadlines, false-positive rules, risk acceptance, and retention."
      />
      <SlaSection />
      <SuppressionSection />
      <GeneralSection />
    </div>
  );
}

function SlaSection() {
  const qc = useQueryClient();
  const { data: policies = [] } = useQuery({
    queryKey: ["sla"],
    queryFn: () => api.get<SlaPolicy[]>("/sla-policies"),
  });
  const { data: zones = [] } = useZones();
  const [drafts, setDrafts] = useState<Record<string, PolicyDraft>>({});
  const [newZone, setNewZone] = useState("");

  const save = useMutation({
    mutationFn: (p: PolicyDraft) =>
      p.id
        ? api.put<{ recomputed: number }>(`/sla-policies/${p.id}`, p)
        : api.post<{ recomputed: number }>("/sla-policies", p),
    onSuccess: (r, p) => {
      toast.success(`Policy saved · ${r.recomputed} due dates updated`);
      setDrafts(({ [String(p.id ?? p.zone)]: _, ...rest }) => rest);
      qc.invalidateQueries({ queryKey: ["sla"] });
      qc.invalidateQueries({ queryKey: ["findings"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/sla-policies/${id}`),
    onSuccess: () => {
      toast.success("Zone policy removed; the default applies");
      qc.invalidateQueries({ queryKey: ["sla"] });
      qc.invalidateQueries({ queryKey: ["findings"] });
    },
  });

  const rows: (PolicyDraft & { key: string })[] = [
    ...policies.map((p) => ({ ...p, ...drafts[String(p.id)], key: String(p.id) })),
    ...Object.entries(drafts)
      .filter(([, d]) => !d.id)
      .map(([key, d]) => ({ ...d, key })),
  ];
  const usedZones = new Set(rows.map((r) => r.zone));
  const edit = (row: PolicyDraft & { key: string }, patch: Partial<PolicyDraft>) => {
    const { key, ...rest } = row;
    setDrafts((d) => ({ ...d, [key]: { ...rest, ...patch } }));
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="SLA policies"
        description="Days to remediate from first detection. A zone policy overrides the default for networks in that zone. Manually set due dates are never changed."
        actions={
          <div className="flex items-center gap-2">
            <Select value={newZone} onChange={(e) => setNewZone(e.target.value)} className="h-8 w-40 text-xs">
              <option value="">Add zone policy…</option>
              {zones
                .filter((z) => !usedZones.has(z))
                .map((z) => (
                  <option key={z} value={z}>
                    {z}
                  </option>
                ))}
            </Select>
            <Button
              size="sm"
              disabled={!newZone}
              onClick={() => {
                const base = policies.find((p) => p.zone === null);
                setDrafts((d) => ({
                  ...d,
                  [newZone]: {
                    zone: newZone,
                    critical_days: base?.critical_days ?? 15,
                    high_days: base?.high_days ?? 30,
                    medium_days: base?.medium_days ?? 90,
                    low_days: base?.low_days ?? 180,
                    enabled: true,
                  },
                }));
                setNewZone("");
              }}
            >
              <Plus className="size-3.5" /> Add
            </Button>
          </div>
        }
      />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-surface-2/60 text-left text-xs text-ink-3">
            <tr>
              <th className="px-4 py-2 font-medium whitespace-nowrap">Applies to</th>
              {SEVS.map((s) => (
                <th key={s.key} className="px-2 py-2 font-medium">
                  <span className="inline-flex items-center gap-1.5">
                    <span className={cn("size-2 rounded-sm", s.cls)} />
                    {s.label}
                  </span>
                </th>
              ))}
              <th className="px-2 py-2 font-medium">Enabled</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((row) => {
              const dirty = !!drafts[row.key];
              return (
                <tr key={row.key}>
                  <td className="px-4 py-2 whitespace-nowrap">
                    {row.zone ?? <span className="font-medium">Default (all zones)</span>}
                  </td>
                  {SEVS.map((s) => (
                    <td key={s.key} className="px-2 py-2">
                      <div className="flex items-center gap-1">
                        <Input
                          type="number"
                          min={1}
                          max={3650}
                          value={row[s.key]}
                          onChange={(e) => edit(row, { [s.key]: Number(e.target.value) })}
                          className="h-8 w-20 text-right font-mono"
                          aria-label={`${s.label} days for ${row.zone ?? "default"}`}
                        />
                        <span className="text-xs text-ink-3">d</span>
                      </div>
                    </td>
                  ))}
                  <td className="px-2 py-2">
                    <input
                      type="checkbox"
                      checked={row.enabled}
                      onChange={(e) => edit(row, { enabled: e.target.checked })}
                      aria-label="Enabled"
                    />
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex justify-end gap-1">
                      {dirty && (
                        <Button
                          size="sm"
                          variant="primary"
                          loading={save.isPending}
                          onClick={() => save.mutate(row)}
                        >
                          Save
                        </Button>
                      )}
                      {row.zone !== null && row.id && (
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label="Remove zone policy"
                          onClick={() => row.id && remove.mutate(row.id)}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function SuppressionSection() {
  const qc = useQueryClient();
  const { data: rules = [] } = useQuery({
    queryKey: ["suppressions"],
    queryFn: () => api.get<SuppressionRule[]>("/suppressions"),
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["suppressions"] });
    qc.invalidateQueries({ queryKey: ["findings"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const toggle = useMutation({
    mutationFn: (r: SuppressionRule) => api.patch(`/suppressions/${r.id}`, { enabled: !r.enabled }),
    onSuccess: refresh,
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/suppressions/${id}`),
    onSuccess: () => {
      toast.success("Rule deleted; its findings are open again");
      refresh();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="False-positive rules"
        description="Created from a finding with “False positive on all hosts”. Applied to existing findings and every future import."
      />
      {rules.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-ink-3">No rules yet.</p>
      ) : (
        <ul className="divide-y divide-line">
          {rules.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    to="/vulnerabilities/$pluginId"
                    params={{ pluginId: String(r.plugin_id) }}
                    className="truncate font-medium hover:text-brand"
                  >
                    {r.plugin_name || `Plugin ${r.plugin_id}`}
                  </Link>
                  <Badge>{r.cidr ?? "all hosts"}</Badge>
                  {r.port != null && <Badge>port {r.port}</Badge>}
                  {!r.enabled && <Badge tone="warn">disabled</Badge>}
                </div>
                <div className="mt-0.5 text-xs text-ink-3">
                  {r.reason} · {r.created_by?.username ?? "unknown"}, {fmtDate(r.created_at)} · {r.matched}{" "}
                  findings suppressed
                </div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => toggle.mutate(r)}>
                {r.enabled ? "Disable" : "Enable"}
              </Button>
              <Button
                size="icon"
                variant="ghost"
                aria-label="Delete rule"
                onClick={() => remove.mutate(r.id)}
              >
                <Trash2 className="size-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function GeneralSection() {
  const qc = useQueryClient();
  const { data } = useAppSettings();
  const [form, setForm] = useState<AppSettings | null>(null);
  useEffect(() => {
    if (data) setForm(data);
  }, [data]);
  const save = useMutation({
    mutationFn: (body: AppSettings) => api.put<AppSettings>("/settings", body),
    onSuccess: (s) => {
      qc.setQueryData(["settings"], s);
      toast.success("Settings saved");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  if (!form) return null;
  const dirty = JSON.stringify(form) !== JSON.stringify(data);
  const set = <K extends keyof AppSettings>(k: K, v: AppSettings[K]) => setForm({ ...form, [k]: v });
  return (
    <Card>
      <CardHeader
        title="Risk acceptance, retention and branding"
        actions={
          <Button
            variant="primary"
            size="sm"
            disabled={!dirty}
            loading={save.isPending}
            onClick={() => save.mutate(form)}
          >
            Save settings
          </Button>
        }
      />
      <div className="grid gap-5 px-4 py-4 md:grid-cols-2">
        <Field label="Longest risk acceptance" hint="Requests cannot ask for a later expiry.">
          <div className="flex items-center gap-2">
            <Input
              type="number"
              min={1}
              max={3650}
              value={form.risk_max_days}
              onChange={(e) => set("risk_max_days", Number(e.target.value))}
              className="w-28 font-mono"
            />
            <span className="text-sm text-ink-3">days</span>
          </div>
        </Field>
        <Field
          label="Self-approval"
          hint="Off: a second admin must approve an admin's own request (four-eyes)."
        >
          <label className="flex h-9 items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.risk_self_approval}
              onChange={(e) => set("risk_self_approval", e.target.checked)}
            />
            Admins may approve their own requests
          </label>
        </Field>
        <Field
          label="Audit log retention"
          hint="Older entries are deleted by the daily job. 0 keeps everything."
        >
          <div className="flex items-center gap-2">
            <Input
              type="number"
              min={0}
              max={3650}
              value={form.audit_retention_days}
              onChange={(e) => set("audit_retention_days", Number(e.target.value))}
              className="w-28 font-mono"
            />
            <span className="text-sm text-ink-3">days</span>
          </div>
        </Field>
        <div />
        <Field label="Company name" hint="Default for new report templates.">
          <Input value={form.branding_company} onChange={(e) => set("branding_company", e.target.value)} />
        </Field>
        <Field label="Classification banner" hint="Default for new report templates.">
          <Input
            value={form.branding_classification}
            onChange={(e) => set("branding_classification", e.target.value)}
          />
        </Field>
      </div>
    </Card>
  );
}
