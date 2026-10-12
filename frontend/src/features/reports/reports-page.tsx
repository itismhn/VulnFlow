import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Copy,
  Download,
  FileSpreadsheet,
  FileText,
  Loader2,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Dialog, DropdownMenu, MenuItem } from "@/components/ui/overlay";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Select,
  Textarea,
} from "@/components/ui/primitives";
import { useAppSettings } from "@/features/workflow/risk-dialog";
import { api, downloadUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useNetworks, useZones } from "@/lib/queries";
import type {
  FindingFilters,
  FindingStatus,
  Page,
  ReportFormat,
  ReportJob,
  ReportTemplate,
  TemplateConfig,
  TemplateKind,
} from "@/lib/types";
import { cn, fmtBytes, fmtDate, SEVERITIES, STATUS_LABELS } from "@/lib/utils";

const KIND_LABEL: Record<TemplateKind, string> = {
  executive: "Executive",
  technical: "Technical",
  network: "By network",
};

const SECTIONS: { key: string; label: string; kinds: TemplateKind[] }[] = [
  { key: "summary", label: "Summary paragraph", kinds: ["executive", "technical", "network"] },
  { key: "kpis", label: "Key figures", kinds: ["executive", "technical"] },
  { key: "charts", label: "Risk charts (severity, trend, age)", kinds: ["executive", "technical"] },
  { key: "top_vulns", label: "Top vulnerabilities", kinds: ["executive", "technical"] },
  { key: "top_hosts", label: "Most at-risk assets", kinds: ["executive", "technical"] },
  { key: "zones", label: "Exposure by zone", kinds: ["executive", "technical"] },
  { key: "recommendations", label: "Recommendations", kinds: ["executive"] },
  { key: "details", label: "Detailed findings", kinds: ["technical"] },
  { key: "networks", label: "One section per network", kinds: ["network"] },
];

const FORMAT_ICON: Record<ReportFormat, React.ReactNode> = {
  pdf: <FileText className="size-4" />,
  html: <FileText className="size-4" />,
  xlsx: <FileSpreadsheet className="size-4" />,
  csv: <FileSpreadsheet className="size-4" />,
};

export function ReportsPage({ initialFilters }: { initialFilters?: string }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const { data: settings } = useAppSettings();
  const preset = (() => {
    try {
      return initialFilters ? (JSON.parse(initialFilters) as FindingFilters) : undefined;
    } catch {
      return undefined;
    }
  })();
  const [generating, setGenerating] = useState<ReportTemplate | null>(null);
  const [editing, setEditing] = useState<Partial<ReportTemplate> | null>(null);

  const { data: templates = [] } = useQuery({
    queryKey: ["report-templates"],
    queryFn: () => api.get<ReportTemplate[]>("/report-templates"),
  });
  const { data: jobs } = useQuery({
    queryKey: ["reports"],
    queryFn: () => api.get<Page<ReportJob>>("/reports", { page_size: 50 }),
    refetchInterval: (q) =>
      q.state.data?.items.some((j) => j.status === "queued" || j.status === "running") ? 2000 : false,
  });
  const removeJob = useMutation({
    mutationFn: (id: number) => api.del(`/reports/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports"] }),
  });
  const removeTemplate = useMutation({
    mutationFn: (id: number) => api.del(`/report-templates/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["report-templates"] });
      toast.success("Template deleted");
    },
  });

  return (
    <div className="animate-in">
      <PageHeader
        title="Reports"
        description="Generate branded PDF, Excel, CSV or HTML reports from a template. Reports contain only the data you can see."
        actions={
          can("templates:manage") && (
            <Button
              variant="primary"
              onClick={() =>
                setEditing({
                  kind: "technical",
                  config: {
                    sections: ["summary", "kpis", "details"],
                    filters: {},
                    branding: {
                      company_name: settings?.branding_company ?? "",
                      classification: settings?.branding_classification || "CONFIDENTIAL - INTERNAL USE ONLY",
                      primary_color: "#0e7490",
                      footer_text: "",
                    },
                    intro: "",
                    top_n: 10,
                    group_by: "plugin",
                  },
                })
              }
            >
              <Plus className="size-4" /> New template
            </Button>
          )
        }
      />

      {preset && (
        <Card className="mb-4 border-brand/30 bg-brand-soft/40 px-4 py-3 text-sm">
          The filters from your findings view will be applied. Choose a template below to generate the report.
        </Card>
      )}

      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {templates.map((t) => (
          <Card key={t.id} className="flex flex-col p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-display font-semibold">{t.name}</h3>
                  <Badge tone={t.builtin ? "neutral" : "brand"}>
                    {t.builtin ? "Built-in" : KIND_LABEL[t.kind]}
                  </Badge>
                </div>
                <p className="mt-1 text-sm text-ink-2">{t.description || "Custom template"}</p>
              </div>
              {can("templates:manage") && (
                <DropdownMenu
                  trigger={
                    <Button size="icon" variant="ghost" aria-label="Template actions">
                      <Pencil className="size-3.5" />
                    </Button>
                  }
                >
                  <MenuItem
                    onSelect={() =>
                      setEditing({ ...t, id: undefined, builtin: false, name: `${t.name} (copy)` })
                    }
                  >
                    <Copy className="size-4" /> Duplicate
                  </MenuItem>
                  {!t.builtin && (
                    <>
                      <MenuItem onSelect={() => setEditing(t)}>
                        <Pencil className="size-4" /> Edit
                      </MenuItem>
                      <MenuItem danger onSelect={() => removeTemplate.mutate(t.id)}>
                        <Trash2 className="size-4" /> Delete
                      </MenuItem>
                    </>
                  )}
                </DropdownMenu>
              )}
            </div>
            <div className="mt-3 flex flex-wrap gap-1">
              {(t.config.sections ?? []).map((s) => (
                <span key={s} className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-3">
                  {SECTIONS.find((x) => x.key === s)?.label ?? s}
                </span>
              ))}
            </div>
            <div className="mt-auto pt-4">
              <Button variant="primary" size="sm" onClick={() => setGenerating(t)}>
                Generate report
              </Button>
            </div>
          </Card>
        ))}
      </div>

      <Card className="overflow-hidden">
        <CardHeader
          title="Generated reports"
          description="Your report history. Files stay available until deleted."
        />
        {!jobs?.items.length ? (
          <EmptyState icon={<FileText className="size-8" />} title="No reports yet">
            Generate one from a template above.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-line">
            {jobs.items.map((j) => (
              <li key={j.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <span className="text-ink-3">{FORMAT_ICON[j.format]}</span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{j.name}</div>
                  <div className="text-xs text-ink-3">
                    {j.template?.name ?? "Deleted template"} · {j.format.toUpperCase()} ·{" "}
                    {fmtDate(j.created_at, true)} · {j.created_by?.username}
                    {j.status === "done" && ` · ${fmtBytes(j.size_bytes)}`}
                  </div>
                  {j.status === "failed" && (
                    <div className="mt-1 flex items-center gap-1 text-xs text-critical">
                      <AlertTriangle className="size-3" /> {j.error}
                    </div>
                  )}
                </div>
                {j.status === "queued" || j.status === "running" ? (
                  <Badge tone="brand">
                    <Loader2 className="size-3 animate-spin" /> Generating
                  </Badge>
                ) : j.status === "done" ? (
                  <a href={downloadUrl(`/reports/${j.id}/download`)}>
                    <Button size="sm">
                      <Download className="size-3.5" /> Download
                    </Button>
                  </a>
                ) : null}
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="Delete report"
                  onClick={() => removeJob.mutate(j.id)}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {generating && (
        <GenerateDialog template={generating} preset={preset} onClose={() => setGenerating(null)} />
      )}
      {editing && <TemplateDialog initial={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ScopeFields({ value, onChange }: { value: FindingFilters; onChange: (f: FindingFilters) => void }) {
  const { data: networks = [] } = useNetworks();
  const { data: zones = [] } = useZones();
  const toggle = <T,>(list: T[] | undefined, v: T) => {
    const s = new Set(list ?? []);
    if (s.has(v)) s.delete(v);
    else s.add(v);
    return s.size ? [...s] : undefined;
  };
  return (
    <div className="space-y-3">
      <Field label="Severities" hint="None selected means low and above">
        <div className="flex flex-wrap gap-1.5">
          {SEVERITIES.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => onChange({ ...value, severity: toggle(value.severity, s.value) })}
              className={cn(
                "rounded-md border px-2.5 py-1 text-xs",
                value.severity?.includes(s.value)
                  ? "border-brand bg-brand-soft text-brand"
                  : "border-line text-ink-2",
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
      </Field>
      <Field label="Statuses" hint="None selected means open, in progress and reopened">
        <div className="flex flex-wrap gap-1.5">
          {(Object.keys(STATUS_LABELS) as FindingStatus[]).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onChange({ ...value, status: toggle(value.status, s) })}
              className={cn(
                "rounded-md border px-2.5 py-1 text-xs",
                value.status?.includes(s)
                  ? "border-brand bg-brand-soft text-brand"
                  : "border-line text-ink-2",
              )}
            >
              {STATUS_LABELS[s]}
            </button>
          ))}
        </div>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Network">
          <Select
            value={value.network_id?.[0] ?? ""}
            onChange={(e) =>
              onChange({ ...value, network_id: e.target.value ? [Number(e.target.value)] : undefined })
            }
          >
            <option value="">All networks</option>
            {networks.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name} ({n.cidr})
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Zone">
          <Select
            value={value.zone?.[0] ?? ""}
            onChange={(e) => onChange({ ...value, zone: e.target.value ? [e.target.value] : undefined })}
          >
            <option value="">All zones</option>
            {zones.map((z) => (
              <option key={z}>{z}</option>
            ))}
          </Select>
        </Field>
        <Field label="IP or CIDR">
          <Input
            value={value.ip ?? ""}
            onChange={(e) => onChange({ ...value, ip: e.target.value || undefined })}
            className="font-mono text-xs"
            placeholder="10.20.0.0/24"
          />
        </Field>
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input
            type="checkbox"
            className="accent-[var(--brand)]"
            checked={!!value.exploitable}
            onChange={(e) => onChange({ ...value, exploitable: e.target.checked || undefined })}
          />
          Exploitable only
        </label>
      </div>
    </div>
  );
}

function GenerateDialog({
  template,
  preset,
  onClose,
}: {
  template: ReportTemplate;
  preset?: FindingFilters;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [format, setFormat] = useState<ReportFormat>("pdf");
  const [name, setName] = useState(template.name);
  const [filters, setFilters] = useState<FindingFilters>(preset ?? template.config.filters ?? {});
  const create = useMutation({
    mutationFn: () => api.post<ReportJob>("/reports", { template_id: template.id, format, name, filters }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reports"] });
      toast.success("Report queued. It will appear in the list when ready.");
      onClose();
    },
  });
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Generate: ${template.name}`}
      className="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={create.isPending} onClick={() => create.mutate()}>
            Generate report
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_160px]">
          <Field label="Report title">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Format">
            <Select value={format} onChange={(e) => setFormat(e.target.value as ReportFormat)}>
              <option value="pdf">PDF</option>
              <option value="xlsx">Excel (.xlsx)</option>
              <option value="html">HTML</option>
              <option value="csv">CSV (findings only)</option>
            </Select>
          </Field>
        </div>
        <div className="border-t border-line pt-4">
          <h4 className="mb-3 font-display text-sm font-semibold">Scope</h4>
          <ScopeFields value={filters} onChange={setFilters} />
        </div>
      </div>
    </Dialog>
  );
}

function TemplateDialog({ initial, onClose }: { initial: Partial<ReportTemplate>; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(initial.name ?? "");
  const [description, setDescription] = useState(initial.description ?? "");
  const [kind, setKind] = useState<TemplateKind>(initial.kind ?? "technical");
  const [config, setConfig] = useState<TemplateConfig>(initial.config as TemplateConfig);
  const setBranding = (k: keyof TemplateConfig["branding"], v: string) =>
    setConfig((c) => ({ ...c, branding: { ...c.branding, [k]: v } }));
  const save = useMutation({
    mutationFn: () =>
      initial.id
        ? api.patch(`/report-templates/${initial.id}`, { name, description, config })
        : api.post("/report-templates", { name, description, kind, config }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["report-templates"] });
      toast.success(initial.id ? "Template saved" : "Template created");
      onClose();
    },
  });
  const available = SECTIONS.filter((s) => s.kinds.includes(kind));

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={initial.id ? "Edit template" : "New report template"}
      className="max-w-2xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!name.trim() || !config.sections.length}
            loading={save.isPending}
            onClick={() => save.mutate()}
          >
            {initial.id ? "Save template" : "Create template"}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Monthly PCI zone report"
            />
          </Field>
          <Field label="Type">
            <Select
              value={kind}
              disabled={!!initial.id}
              onChange={(e) => {
                const k = e.target.value as TemplateKind;
                setKind(k);
                setConfig((c) => ({
                  ...c,
                  sections: c.sections.filter((s) => SECTIONS.find((x) => x.key === s)?.kinds.includes(k)),
                }));
              }}
            >
              <option value="executive">Executive summary</option>
              <option value="technical">Technical detail</option>
              <option value="network">By network range</option>
            </Select>
          </Field>
          <Field label="Description" className="sm:col-span-2">
            <Input value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
        </div>

        <section>
          <h4 className="mb-2 font-display text-sm font-semibold">Sections</h4>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {available.map((s) => (
              <label key={s.key} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="accent-[var(--brand)]"
                  checked={config.sections.includes(s.key)}
                  onChange={(e) =>
                    setConfig((c) => ({
                      ...c,
                      sections: e.target.checked
                        ? available.map((a) => a.key).filter((k) => k === s.key || c.sections.includes(k))
                        : c.sections.filter((x) => x !== s.key),
                    }))
                  }
                />
                {s.label}
              </label>
            ))}
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field label="Items in “top” lists">
              <Input
                type="number"
                min={1}
                max={100}
                value={config.top_n}
                onChange={(e) => setConfig((c) => ({ ...c, top_n: Number(e.target.value) || 10 }))}
              />
            </Field>
            {kind === "technical" && (
              <Field label="Group detailed findings by">
                <Select
                  value={config.group_by}
                  onChange={(e) =>
                    setConfig((c) => ({ ...c, group_by: e.target.value as "host" | "plugin" }))
                  }
                >
                  <option value="plugin">Vulnerability</option>
                  <option value="host">Host</option>
                </Select>
              </Field>
            )}
          </div>
          <Field label="Introduction text" className="mt-3" hint="Shown in the summary section">
            <Textarea
              value={config.intro}
              onChange={(e) => setConfig((c) => ({ ...c, intro: e.target.value }))}
            />
          </Field>
        </section>

        <section>
          <h4 className="mb-2 font-display text-sm font-semibold">Branding</h4>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Company name">
              <Input
                value={config.branding.company_name}
                onChange={(e) => setBranding("company_name", e.target.value)}
              />
            </Field>
            <Field label="Accent colour">
              <div className="flex gap-2">
                <input
                  type="color"
                  value={config.branding.primary_color}
                  onChange={(e) => setBranding("primary_color", e.target.value)}
                  className="h-9 w-12 cursor-pointer rounded-md border border-line bg-surface"
                  aria-label="Accent colour"
                />
                <Input
                  value={config.branding.primary_color}
                  onChange={(e) => setBranding("primary_color", e.target.value)}
                  className="font-mono"
                />
              </div>
            </Field>
            <Field label="Classification banner">
              <Input
                value={config.branding.classification}
                onChange={(e) => setBranding("classification", e.target.value)}
              />
            </Field>
            <Field label="Footer text">
              <Input
                value={config.branding.footer_text}
                onChange={(e) => setBranding("footer_text", e.target.value)}
              />
            </Field>
          </div>
        </section>

        <section>
          <h4 className="mb-2 font-display text-sm font-semibold">Default scope</h4>
          <ScopeFields
            value={config.filters ?? {}}
            onChange={(filters) => setConfig((c) => ({ ...c, filters }))}
          />
        </section>
      </div>
    </Dialog>
  );
}
