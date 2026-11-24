import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Copy,
  Download,
  FileSpreadsheet,
  FileText,
  LayoutTemplate,
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
} from "@/components/ui/primitives";
import { useAppSettings } from "@/features/workflow/risk-dialog";
import { api, downloadUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  FindingFilters,
  Page,
  ReportFormat,
  ReportJob,
  ReportTemplate,
  TemplateKind,
} from "@/lib/types";
import { fmtBytes, fmtDate } from "@/lib/utils";
import { assetUrl, defaultConfig, ReportEditor } from "./report-editor";
import { ScopeFields } from "./report-scope";

const KIND_LABEL: Record<TemplateKind, string> = {
  executive: "Executive",
  technical: "Technical",
  network: "By network",
};

const MAIN_TEMPLATE_NAMES = new Set(["Executive Summary", "Technical Detailed", "Network / Range Report"]);

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

const FORMAT_ICON: Record<string, React.ReactNode> = {
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
  const [showMoreTemplates, setShowMoreTemplates] = useState(false);

  const { data: templates = [] } = useQuery({
    queryKey: ["report-templates"],
    queryFn: () => api.get<ReportTemplate[]>("/report-templates"),
  });
  const mainTemplates = templates.filter((t) => t.builtin && MAIN_TEMPLATE_NAMES.has(t.name));
  const additionalTemplates = templates.filter((t) => t.builtin && !MAIN_TEMPLATE_NAMES.has(t.name));
  const customTemplates = templates.filter((t) => !t.builtin);
  const visibleTemplates = [
    ...mainTemplates,
    ...(showMoreTemplates ? additionalTemplates : []),
    ...customTemplates,
  ];
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
        description="Design branded reports with your own backgrounds, logos, text, and page layouts."
        actions={
          can("templates:manage") && (
            <div className="flex flex-wrap gap-2">
              <Button
                variant="primary"
                onClick={() =>
                  setEditing({ kind: "technical", config: defaultConfig(settings?.branding_company ?? "") })
                }
              >
                <Plus className="size-4" />
                New template
              </Button>
            </div>
          )
        }
      />

      {preset && (
        <Card className="mb-4 border-brand/30 bg-brand-soft/40 px-4 py-3 text-sm">
          The filters from your findings view will be applied. Choose a template below to generate the report.
        </Card>
      )}

      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-lg font-semibold">Report templates</h2>
        <div className="flex items-center gap-3">
          <span className="text-sm text-ink-3">
            {templates.length} templates · your branding, your content
          </span>
          {additionalTemplates.length > 0 && (
            <Button
              size="sm"
              aria-expanded={showMoreTemplates}
              onClick={() => setShowMoreTemplates((shown) => !shown)}
            >
              {showMoreTemplates
                ? "Show fewer templates"
                : `Show ${additionalTemplates.length} more templates`}
            </Button>
          )}
        </div>
      </div>
      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {visibleTemplates.map((t) => (
          <Card key={t.id} className="flex flex-col overflow-hidden">
            <TemplateThumbnail template={t} />
            <div className="flex flex-1 flex-col p-4">
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
                    {t.config.custom_sections?.find((x) => x.id === s)?.title ??
                      SECTIONS.find((x) => x.key === s)?.label ??
                      s}
                  </span>
                ))}
              </div>
              <div className="mt-auto pt-4">
                <Button variant="primary" size="sm" onClick={() => setGenerating(t)}>
                  Generate report
                </Button>
              </div>
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
                <span className="text-ink-3">{FORMAT_ICON[j.format] ?? <FileText className="size-4" />}</span>
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
      {editing && <ReportEditor initial={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function TemplateThumbnail({ template }: { template: ReportTemplate }) {
  const page = template.config.opening_pages?.[0];
  return (
    <div
      className="relative flex h-36 items-end overflow-hidden border-b border-line px-5 py-4"
      style={{
        backgroundColor: page?.background_color ?? "#102c46",
        backgroundImage: page?.background_asset ? `url(${assetUrl(page.background_asset)})` : undefined,
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
    >
      <div className="absolute inset-0 bg-black/15" />
      <div className="absolute right-3 top-3 rounded bg-white/15 px-2 py-1 text-xs text-white">
        {page ? `${template.config.opening_pages?.length} opening page(s)` : "Built-in layout"}
      </div>
      <div className="relative text-white">
        <div className="mb-1 text-xs uppercase tracking-wider text-white/70">
          {template.config.branding.company_name || "VulnFlow"}
        </div>
        <div className="flex items-center gap-2 font-display text-xl font-semibold">
          <LayoutTemplate className="size-5" />
          {template.name}
        </div>
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
  const [config, setConfig] = useState(template.config);
  const [format, setFormat] = useState<ReportFormat>("pdf");
  const [customizing, setCustomizing] = useState(false);
  const [name, setName] = useState(template.name);
  const [filters, setFilters] = useState<FindingFilters>(preset ?? template.config.filters ?? {});
  const create = useMutation({
    mutationFn: () =>
      api.post<ReportJob>("/reports", { template_id: template.id, format, name, filters, config }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reports"] });
      toast.success("Report queued. It will appear in the list when ready.");
      onClose();
    },
  });
  return (
    <>
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
          <div className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface-2 p-3">
            <div className="text-sm">
              <div className="font-medium">Make it specific to this report</div>
              <p className="text-xs text-ink-3">Edit text and design without changing the saved template.</p>
            </div>
            <Button size="sm" onClick={() => setCustomizing(true)}>
              <Pencil className="size-3.5" />
              Customize
            </Button>
          </div>
          <div className="border-t border-line pt-4">
            <h4 className="mb-3 font-display text-sm font-semibold">Scope</h4>
            <ScopeFields value={filters} onChange={setFilters} />
          </div>
        </div>
      </Dialog>
      {customizing && (
        <ReportEditor
          initial={{ ...template, name, config: { ...config, filters } }}
          reportOnly
          onApply={(next, title) => {
            setConfig(next);
            setName(title);
            setFilters(next.filters);
          }}
          onClose={() => setCustomizing(false)}
        />
      )}
    </>
  );
}
