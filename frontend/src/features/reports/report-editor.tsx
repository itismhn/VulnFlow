import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Eye, LayoutTemplate, Plus, Save, Trash2, Type, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Dialog } from "@/components/ui/overlay";
import { Badge, Button, Field, Input, Select, Textarea } from "@/components/ui/primitives";
import { api, downloadUrl, request } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  OpeningPage,
  PageBlock,
  ReportLayout,
  ReportTemplate,
  TemplateConfig,
  TemplateKind,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { ScopeFields } from "./report-scope";

const SECTION_NAMES: Record<string, string> = {
  summary: "Summary",
  kpis: "Key figures",
  charts: "Risk overview",
  top_vulns: "Top vulnerabilities",
  top_hosts: "Most at-risk assets",
  zones: "Exposure by zone",
  recommendations: "Recommendations",
  details: "Detailed findings",
  networks: "Network breakdown",
};
const LAYOUT: ReportLayout = {
  page_size: "A4",
  orientation: "portrait",
  font: "sans-serif",
  font_size: 10,
  margin_mm: 18,
  page_numbers: true,
  show_cover: true,
};
const uid = () => crypto.randomUUID();
export const assetUrl = (id: string) => downloadUrl(`/report-assets/${id}`);
const makeBlock = (text = "Your text", extra: Partial<PageBlock> = {}): PageBlock => ({
  id: uid(),
  type: "text",
  text,
  x: 12,
  y: 40,
  width: 76,
  font_size: 24,
  color: "#ffffff",
  bold: false,
  align: "left",
  ...extra,
});
const makePage = (): OpeningPage => ({
  id: uid(),
  background_color: "#102c46",
  background_fit: "cover",
  overlay: 0,
  blocks: [
    makeBlock("{{ company.name }}", { y: 12, font_size: 14, color: "#9ddde4" }),
    makeBlock("{{ report.title }}", { y: 35, font_size: 36, bold: true }),
    makeBlock("Vulnerability assessment\n{{ report.date }}", { y: 58, font_size: 14 }),
    makeBlock("{{ company.classification }}", { y: 88, font_size: 9, color: "#9ddde4" }),
  ],
});
export function defaultConfig(company = ""): TemplateConfig {
  return {
    sections: ["summary", "kpis", "details"],
    filters: {},
    branding: {
      company_name: company,
      classification: "CONFIDENTIAL",
      primary_color: "#0e7490",
      footer_text: "",
    },
    intro: "",
    top_n: 10,
    group_by: "plugin",
    opening_pages: [makePage()],
    layout: { ...LAYOUT },
    custom_sections: [],
    section_titles: {},
  };
}
function normalize(config?: TemplateConfig) {
  const fallback = defaultConfig();
  return {
    ...fallback,
    ...config,
    branding: { ...fallback.branding, ...config?.branding },
    opening_pages: config?.opening_pages ?? [],
    layout: { ...LAYOUT, ...config?.layout },
    custom_sections: config?.custom_sections ?? [],
    section_titles: config?.section_titles ?? {},
    page_breaks: config?.page_breaks ?? [],
  };
}
type Design = ReturnType<typeof normalize>;
type Asset = { id: string; filename: string };
async function upload(file: File): Promise<Asset> {
  const form = new FormData();
  form.append("file", file);
  return api.upload<Asset>("/report-assets", form);
}
function UploadField({
  label,
  accept = "image/png,image/jpeg",
  onUpload,
}: {
  label: string;
  accept?: string;
  onUpload: (a: Asset) => void;
}) {
  const [busy, setBusy] = useState(false);
  const { can } = useAuth();
  if (!can("templates:manage")) return null;
  return (
    <label
      className={cn(
        "inline-flex cursor-pointer items-center gap-2 rounded-md border border-line bg-surface px-3 py-2 text-sm hover:bg-surface-2",
        busy && "pointer-events-none opacity-50",
      )}
    >
      <Upload className="size-4" />
      {busy ? "Uploading…" : label}
      <input
        type="file"
        accept={accept}
        disabled={busy}
        className="sr-only"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          setBusy(true);
          try {
            onUpload(await upload(file));
          } catch (error) {
            toast.error(error instanceof Error ? error.message : "Upload failed");
          } finally {
            setBusy(false);
            e.target.value = "";
          }
        }}
      />
    </label>
  );
}
function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Field label={label}>
      <div className="flex gap-2">
        <input
          type="color"
          aria-label={label}
          value={/^#[0-9a-f]{6}$/i.test(value) ? value : "#000000"}
          onChange={(e) => onChange(e.target.value)}
          className="h-9 w-10 cursor-pointer rounded border border-line"
        />
        <Input
          value={value}
          maxLength={7}
          aria-label={`${label} hex value`}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    </Field>
  );
}
function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  return (
    <Field label={label}>
      <Input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={(e) => onChange(Math.max(min, Math.min(max, Number(e.target.value) || min)))}
      />
    </Field>
  );
}
function move<T>(items: T[], index: number, delta: number) {
  const result = [...items];
  [result[index], result[index + delta]] = [result[index + delta], result[index]];
  return result;
}

export function ReportEditor({
  initial,
  onClose,
  reportOnly,
  onApply,
}: {
  initial: Partial<ReportTemplate>;
  onClose: () => void;
  reportOnly?: boolean;
  onApply?: (config: TemplateConfig, title: string) => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState(initial.name ?? "Untitled report template");
  const [description, setDescription] = useState(initial.description ?? "");
  const [kind, setKind] = useState<TemplateKind>(initial.kind ?? "technical");
  const [config, setConfig] = useState<Design>(() => normalize(initial.config ?? defaultConfig()));
  const [tab, setTab] = useState("pages");
  const [pageIndex, setPageIndex] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewPdf, setPreviewPdf] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const page = config.opening_pages[pageIndex];
  const block = page?.blocks.find((b) => b.id === selected);
  const drag = useRef<{
    id: string;
    x: number;
    y: number;
    clientX: number;
    clientY: number;
    width: number;
    height: number;
  } | null>(null);
  const patch = (change: Partial<Design>) => setConfig((c) => ({ ...c, ...change }));
  const patchPage = (change: Partial<OpeningPage>) =>
    setConfig((c) => ({
      ...c,
      opening_pages: c.opening_pages.map((p, i) => (i === pageIndex ? { ...p, ...change } : p)),
    }));
  const patchBlock = (change: Partial<PageBlock>) =>
    setConfig((c) => ({
      ...c,
      opening_pages: c.opening_pages.map((p, i) =>
        i === pageIndex
          ? { ...p, blocks: p.blocks.map((b) => (b.id === selected ? { ...b, ...change } : b)) }
          : p,
      ),
    }));
  const patchBrand = (change: Partial<TemplateConfig["branding"]>) =>
    setConfig((c) => ({ ...c, branding: { ...c.branding, ...change } }));
  const patchLayout = (change: Partial<ReportLayout>) =>
    setConfig((c) => ({ ...c, layout: { ...c.layout, ...change } }));
  const save = useMutation({
    mutationFn: () =>
      initial.id
        ? api.patch(`/report-templates/${initial.id}`, { name, description, config })
        : api.post("/report-templates", { name, description, kind, config }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["report-templates"] });
      toast.success("Template saved");
      onClose();
    },
  });
  const closePreview = () => {
    setPreview(null);
    if (previewPdf) URL.revokeObjectURL(previewPdf);
    setPreviewPdf(null);
  };
  const showPreview = async (format: "html" | "pdf") => {
    setPreviewBusy(true);
    try {
      const res = await request<Response>("POST", `/report-preview?format=${format}`, {
        body: { name, kind, config },
        raw: true,
      });
      if (format === "html") setPreview(await res.text());
      else {
        const url = URL.createObjectURL(await res.blob());
        setPreviewPdf(url);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Preview failed");
    } finally {
      setPreviewBusy(false);
    }
  };
  const expand = (text: string) =>
    text.replace(
      /\{\{\s*([\w.]+)\s*\}\}/g,
      (match, key) =>
        ({
          "company.name": config.branding.company_name || "Your company",
          "report.title": name,
          "report.date": new Date().toLocaleDateString(),
          "company.classification": config.branding.classification,
          "report.author": "Report author",
          "report.scope": "Selected report scope",
          "metrics.total_open": "—",
          "metrics.assets": "—",
        })[key as "company.name"] ?? match,
    );
  const pageWidth = config.layout.page_size === "A4" ? 210 : 215.9;
  const pageHeight = config.layout.page_size === "A4" ? 297 : 279.4;
  const landscape = config.layout.orientation === "landscape";
  const addBlock = (newBlock: PageBlock) => {
    patchPage({ blocks: [...page.blocks, newBlock] });
    setSelected(newBlock.id);
  };
  const disabled = !name.trim();
  const title = reportOnly
    ? "Customize this report"
    : initial.id
      ? "Edit report template"
      : "Create report template";
  return (
    <>
      <Dialog
        open
        title={title}
        description="Design your opening pages, branding, report content, and page layout."
        onOpenChange={(o) => {
          if (!o) onClose();
        }}
        className="max-w-[1320px]"
        footer={
          <>
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={disabled}
              loading={save.isPending}
              onClick={() => {
                if (reportOnly) {
                  onApply?.(config, name);
                  onClose();
                } else save.mutate();
              }}
            >
              <Save className="size-4" />
              {reportOnly ? "Apply to this report" : "Save template"}
            </Button>
          </>
        }
      >
        <div className="mb-5 flex flex-wrap justify-end gap-2">
          <Button disabled={disabled} loading={previewBusy} onClick={() => showPreview("html")}>
            <Eye className="size-4" />
            Preview report
          </Button>
          <Button disabled={disabled} loading={previewBusy} onClick={() => showPreview("pdf")}>
            PDF proof
          </Button>
        </div>
        <div className="mb-5 grid gap-3 sm:grid-cols-[2fr_1fr]">
          <Field label={reportOnly ? "Report title" : "Template name"}>
            <Input
              value={name}
              maxLength={reportOnly ? 255 : 128}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <Field label="Report type">
            <Select
              value={kind}
              disabled={!!initial.id}
              onChange={(e) => setKind(e.target.value as TemplateKind)}
            >
              <option value="technical">Technical findings</option>
              <option value="executive">Executive summary</option>
              <option value="network">Network report</option>
            </Select>
          </Field>
        </div>
        <div className="mt-5 border-b border-line" role="tablist" aria-label="Template settings">
          {["pages", "branding", "content", "layout"].map((key) => (
            <button
              type="button"
              role="tab"
              aria-selected={tab === key}
              key={key}
              onClick={() => {
                setTab(key);
                setSelected(null);
              }}
              className={cn(
                "border-b-2 px-4 py-3 text-sm capitalize",
                tab === key ? "border-brand font-medium text-brand" : "border-transparent text-ink-2",
              )}
            >
              {key === "pages" ? "Opening pages" : key}
            </button>
          ))}
        </div>
        <div className="pt-5">
          {tab === "pages" && (
            <div className="grid gap-5 lg:grid-cols-[180px_minmax(240px,1fr)_280px]">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-semibold">Opening pages</h4>
                  <Badge>{config.opening_pages.length}/10</Badge>
                </div>
                {config.opening_pages.map((p, i) => (
                  <div
                    key={p.id}
                    className={cn(
                      "rounded-lg border p-2",
                      i === pageIndex ? "border-brand bg-brand-soft" : "border-line",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        setPageIndex(i);
                        setSelected(null);
                      }}
                      className="flex w-full items-center gap-2 text-left text-sm"
                    >
                      <span
                        className="flex h-10 w-8 shrink-0 items-center justify-center rounded-sm text-xs text-white"
                        style={{
                          backgroundColor: p.background_color,
                          backgroundImage: p.background_asset
                            ? `url(${assetUrl(p.background_asset)})`
                            : undefined,
                          backgroundSize: "cover",
                        }}
                      >
                        {i + 1}
                      </span>
                      {i === 0 ? "Cover" : `Opening page ${i + 1}`}
                    </button>
                    <div className="mt-2 flex justify-end gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`Move page ${i + 1} up`}
                        disabled={i === 0}
                        onClick={() => {
                          patch({ opening_pages: move(config.opening_pages, i, -1) });
                          setPageIndex(i - 1);
                        }}
                      >
                        <ArrowUp className="size-3" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`Move page ${i + 1} down`}
                        disabled={i === config.opening_pages.length - 1}
                        onClick={() => {
                          patch({ opening_pages: move(config.opening_pages, i, 1) });
                          setPageIndex(i + 1);
                        }}
                      >
                        <ArrowDown className="size-3" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`Delete page ${i + 1}`}
                        onClick={() => {
                          patch({ opening_pages: config.opening_pages.filter((x) => x.id !== p.id) });
                          setPageIndex(0);
                          setSelected(null);
                        }}
                      >
                        <Trash2 className="size-3" />
                      </Button>
                    </div>
                  </div>
                ))}
                <Button
                  className="w-full"
                  disabled={config.opening_pages.length >= 10}
                  onClick={() => {
                    patch({
                      opening_pages: [
                        ...config.opening_pages,
                        { ...makePage(), blocks: [makeBlock("Your opening page", { y: 20, bold: true })] },
                      ],
                    });
                    setPageIndex(config.opening_pages.length);
                    setSelected(null);
                  }}
                >
                  <Plus className="size-4" />
                  Add page
                </Button>
                <p className="text-xs text-ink-3">
                  Opening pages appear before your report sections. Select a block to edit it.
                </p>
              </div>
              <div className="rounded-xl border border-line bg-surface-2 p-4">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-medium uppercase tracking-wider text-ink-3">Page canvas</span>
                  {page && (
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        disabled={page.blocks.length >= 40}
                        onClick={() => addBlock(makeBlock())}
                      >
                        <Type className="size-3.5" />
                        Text
                      </Button>
                      <UploadField
                        label="Image"
                        onUpload={(a) =>
                          addBlock(makeBlock("", { type: "image", asset: a.id, width: 30, y: 15 }))
                        }
                      />
                    </div>
                  )}
                </div>
                {page ? (
                  <div
                    className="mx-auto w-full max-w-[450px] shadow-xl"
                    style={{ containerType: "inline-size" }}
                  >
                    <div
                      role="group"
                      className="relative overflow-hidden"
                      aria-label="Opening page canvas"
                      style={{
                        aspectRatio: landscape ? `${pageHeight}/${pageWidth}` : `${pageWidth}/${pageHeight}`,
                        backgroundColor: page.background_color,
                        backgroundImage: page.background_asset
                          ? `url(${assetUrl(page.background_asset)})`
                          : undefined,
                        backgroundSize: page.background_fit,
                        backgroundPosition: "center",
                        backgroundRepeat: "no-repeat",
                        fontFamily: config.layout.font,
                      }}
                      onPointerMove={(e) => {
                        const d = drag.current;
                        if (!d) return;
                        patchBlock({
                          x: Math.max(
                            0,
                            Math.min(95, Math.round(d.x + ((e.clientX - d.clientX) / d.width) * 100)),
                          ),
                          y: Math.max(
                            0,
                            Math.min(95, Math.round(d.y + ((e.clientY - d.clientY) / d.height) * 100)),
                          ),
                        });
                      }}
                      onPointerUp={() => {
                        drag.current = null;
                      }}
                      onPointerCancel={() => {
                        drag.current = null;
                      }}
                    >
                      <div
                        className="pointer-events-none absolute inset-0 bg-black"
                        style={{ opacity: page.overlay }}
                      />
                      {page.blocks.map((b) => (
                        <button
                          key={b.id}
                          type="button"
                          aria-label={`Select ${b.type} block: ${b.text.slice(0, 40) || "image"}`}
                          onClick={() => setSelected(b.id)}
                          onPointerDown={(e) => {
                            setSelected(b.id);
                            const rect = e.currentTarget.parentElement?.getBoundingClientRect();
                            if (!rect) return;
                            drag.current = {
                              id: b.id,
                              x: b.x,
                              y: b.y,
                              clientX: e.clientX,
                              clientY: e.clientY,
                              width: rect.width,
                              height: rect.height,
                            };
                            e.currentTarget.setPointerCapture(e.pointerId);
                          }}
                          className={cn(
                            "absolute cursor-move touch-none whitespace-pre-wrap break-words border border-transparent p-0 text-left leading-[1.3] hover:border-cyan-300/70 focus-visible:outline-2 focus-visible:outline-cyan-300",
                            selected === b.id && "border-cyan-300 ring-1 ring-cyan-300",
                          )}
                          style={{
                            left: `${b.x}%`,
                            top: `${b.y}%`,
                            width: `${b.width}%`,
                            fontSize: `calc(${b.font_size} * 100cqw / ${(((landscape ? pageHeight : pageWidth) / 25.4) * 72).toFixed(2)})`,
                            color: b.color,
                            fontWeight: b.bold ? 700 : 400,
                            textAlign: b.align,
                          }}
                        >
                          {b.type === "image" && b.asset ? (
                            <img
                              src={assetUrl(b.asset)}
                              alt="Uploaded report element"
                              className="pointer-events-none w-full"
                              draggable={false}
                            />
                          ) : (
                            expand(b.text)
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="flex min-h-80 flex-col items-center justify-center gap-3 text-center text-ink-3">
                    <LayoutTemplate className="size-10" />
                    <p>
                      Add an opening page to design a cover.
                      <br />
                      Without opening pages, the standard cover is used.
                    </p>
                    <Button onClick={() => patch({ opening_pages: [makePage()] })}>Add cover page</Button>
                  </div>
                )}
                <p className="mt-4 text-center text-xs text-ink-3">
                  Drag blocks to position them. Preview report to check actual content and pagination.
                </p>
              </div>
              <div className="space-y-4">
                {page && (
                  <>
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-semibold">
                        {block ? "Selected block" : "Page background"}
                      </h4>
                      {block && (
                        <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>
                          Background
                        </Button>
                      )}
                    </div>
                    {block ? (
                      <>
                        {block.type === "text" && (
                          <Field label="Text" hint="Supports report fields such as {{ report.title }}">
                            <Textarea
                              rows={5}
                              value={block.text}
                              onChange={(e) => patchBlock({ text: e.target.value })}
                            />
                          </Field>
                        )}
                        <div className="grid grid-cols-2 gap-3">
                          <NumberField
                            label="Left (%)"
                            value={block.x}
                            min={0}
                            max={95}
                            onChange={(x) => patchBlock({ x })}
                          />
                          <NumberField
                            label="Top (%)"
                            value={block.y}
                            min={0}
                            max={95}
                            onChange={(y) => patchBlock({ y })}
                          />
                          <NumberField
                            label="Width (%)"
                            value={block.width}
                            min={5}
                            max={100}
                            onChange={(width) => patchBlock({ width })}
                          />
                          {block.type === "text" && (
                            <NumberField
                              label="Size (pt)"
                              value={block.font_size}
                              min={8}
                              max={96}
                              onChange={(font_size) => patchBlock({ font_size })}
                            />
                          )}
                        </div>
                        {block.type === "text" && (
                          <>
                            <ColorField
                              label="Text colour"
                              value={block.color}
                              onChange={(color) => patchBlock({ color })}
                            />
                            <Field label="Alignment">
                              <Select
                                value={block.align}
                                onChange={(e) => patchBlock({ align: e.target.value as PageBlock["align"] })}
                              >
                                <option value="left">Left</option>
                                <option value="center">Center</option>
                                <option value="right">Right</option>
                              </Select>
                            </Field>
                            <label className="flex gap-2 text-sm">
                              <input
                                type="checkbox"
                                checked={block.bold}
                                onChange={(e) => patchBlock({ bold: e.target.checked })}
                              />
                              Bold text
                            </label>
                          </>
                        )}
                        <Button
                          onClick={() => {
                            patchPage({ blocks: page.blocks.filter((b) => b.id !== block.id) });
                            setSelected(null);
                          }}
                        >
                          <Trash2 className="size-4" />
                          Delete block
                        </Button>
                        <div className="border-t border-line pt-3">
                          <p className="mb-2 text-xs text-ink-3">Insert a field into this text</p>
                          <div className="flex flex-wrap gap-1">
                            {["report.title", "report.date", "company.name", "company.classification"].map(
                              (key) => (
                                <button
                                  key={key}
                                  type="button"
                                  className="rounded border border-line px-2 py-1 text-xs text-brand"
                                  onClick={() => patchBlock({ text: `${block.text}\n{{ ${key} }}` })}
                                >
                                  {key}
                                </button>
                              ),
                            )}
                          </div>
                        </div>
                      </>
                    ) : (
                      <>
                        <ColorField
                          label="Background colour"
                          value={page.background_color}
                          onChange={(background_color) => patchPage({ background_color })}
                        />
                        <UploadField
                          label="Upload background"
                          onUpload={(a) => patchPage({ background_asset: a.id })}
                        />
                        {page.background_asset && (
                          <>
                            <img
                              src={assetUrl(page.background_asset)}
                              alt="Background preview"
                              className="max-h-24 w-full rounded object-cover"
                            />
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => patchPage({ background_asset: null })}
                            >
                              Remove background
                            </Button>
                          </>
                        )}
                        <Field label="Background fit">
                          <Select
                            value={page.background_fit}
                            onChange={(e) =>
                              patchPage({ background_fit: e.target.value as "cover" | "contain" })
                            }
                          >
                            <option value="cover">Fill page (crop to fit)</option>
                            <option value="contain">Show entire image</option>
                          </Select>
                        </Field>
                        <Field label={`Dark overlay · ${Math.round(page.overlay * 100)}%`}>
                          <input
                            aria-label="Dark overlay"
                            type="range"
                            min={0}
                            max={0.9}
                            step={0.05}
                            value={page.overlay}
                            onChange={(e) => patchPage({ overlay: Number(e.target.value) })}
                            className="w-full accent-[var(--brand)]"
                          />
                        </Field>
                        <p className="text-xs text-ink-3">
                          Use a high-resolution PNG or JPEG. Add an overlay to keep text readable over
                          photographs.
                        </p>
                      </>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
          {tab === "branding" && (
            <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
              <Field label="Company name">
                <Input
                  value={config.branding.company_name}
                  onChange={(e) => patchBrand({ company_name: e.target.value })}
                />
              </Field>
              <ColorField
                label="Accent colour"
                value={config.branding.primary_color}
                onChange={(primary_color) => patchBrand({ primary_color })}
              />
              <Field label="Classification">
                <Input
                  value={config.branding.classification}
                  onChange={(e) => patchBrand({ classification: e.target.value })}
                />
              </Field>
              <Field label="Header text">
                <Input
                  value={config.branding.header_text ?? ""}
                  onChange={(e) => patchBrand({ header_text: e.target.value })}
                />
              </Field>
              <Field label="Footer text">
                <Input
                  value={config.branding.footer_text}
                  onChange={(e) => patchBrand({ footer_text: e.target.value })}
                />
              </Field>
              <NumberField
                label="Logo width (mm)"
                value={config.branding.logo_width_mm ?? 35}
                min={10}
                max={100}
                onChange={(logo_width_mm) => patchBrand({ logo_width_mm })}
              />
              <div className="space-y-3">
                <UploadField label="Upload company logo" onUpload={(a) => patchBrand({ logo_asset: a.id })} />
                {config.branding.logo_asset && (
                  <>
                    <img
                      src={assetUrl(config.branding.logo_asset)}
                      alt="Company logo"
                      className="max-h-20 max-w-48 object-contain"
                    />
                    <div className="flex flex-wrap gap-2">
                      {page && (
                        <Button
                          size="sm"
                          onClick={() => {
                            addBlock(
                              makeBlock("", {
                                type: "image",
                                asset: config.branding.logo_asset,
                                width: 25,
                                y: 10,
                              }),
                            );
                            setTab("pages");
                          }}
                        >
                          Add logo to page
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" onClick={() => patchBrand({ logo_asset: null })}>
                        Remove logo
                      </Button>
                    </div>
                  </>
                )}
              </div>
              <p className="text-sm text-ink-3 md:col-span-2">
                The accent colour is used for section headings. Upload a logo and add it to any opening page
                to position and size it yourself.
              </p>
            </div>
          )}
          {tab === "content" && (
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="space-y-4">
                <Field label="Template description">
                  <Input value={description} onChange={(e) => setDescription(e.target.value)} />
                </Field>
                <Field label="Introduction">
                  <Textarea
                    rows={3}
                    value={config.intro}
                    onChange={(e) => patch({ intro: e.target.value })}
                  />
                </Field>
                <Field
                  label="Summary text"
                  hint="Leave blank to use the automatic summary in manual reports."
                >
                  <Textarea
                    rows={4}
                    value={config.summary_text ?? ""}
                    onChange={(e) => patch({ summary_text: e.target.value })}
                  />
                </Field>
                <Field
                  label="Recommendations"
                  hint="Leave blank to use automatic recommendations in manual reports."
                >
                  <Textarea
                    rows={4}
                    value={config.recommendations_text ?? ""}
                    onChange={(e) => patch({ recommendations_text: e.target.value })}
                  />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <NumberField
                    label="Top list size"
                    value={config.top_n}
                    min={1}
                    max={100}
                    onChange={(top_n) => patch({ top_n })}
                  />
                  <Field label="Group findings by">
                    <Select
                      value={config.group_by}
                      onChange={(e) => patch({ group_by: e.target.value as "plugin" | "host" })}
                    >
                      <option value="plugin">Vulnerability</option>
                      <option value="host">Host</option>
                    </Select>
                  </Field>
                </div>
              </div>
              <div className="space-y-3">
                <h4 className="text-sm font-semibold">Report sections</h4>
                <p className="text-xs text-ink-3">
                  Reorder sections and change their headings. Opening pages always come first.
                </p>
                {config.sections.map((key, i) => {
                  const custom = config.custom_sections.find((s) => s.id === key);
                  return (
                    <div key={key} className="rounded-lg border border-line p-3">
                      <div className="flex items-center gap-2">
                        <Input
                          aria-label={`Heading for ${SECTION_NAMES[key] ?? "custom section"}`}
                          value={custom?.title ?? config.section_titles[key] ?? SECTION_NAMES[key] ?? key}
                          onChange={(e) =>
                            custom
                              ? patch({
                                  custom_sections: config.custom_sections.map((s) =>
                                    s.id === key ? { ...s, title: e.target.value } : s,
                                  ),
                                })
                              : patch({
                                  section_titles: { ...config.section_titles, [key]: e.target.value },
                                })
                          }
                        />
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label={`Move ${key} up`}
                          disabled={i === 0}
                          onClick={() => patch({ sections: move(config.sections, i, -1) })}
                        >
                          <ArrowUp className="size-3" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label={`Move ${key} down`}
                          disabled={i === config.sections.length - 1}
                          onClick={() => patch({ sections: move(config.sections, i, 1) })}
                        >
                          <ArrowDown className="size-3" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label={`Remove ${key}`}
                          onClick={() =>
                            patch({
                              sections: config.sections.filter((s) => s !== key),
                              custom_sections: config.custom_sections.filter((s) => s.id !== key),
                              page_breaks: config.page_breaks.filter((s) => s !== key),
                            })
                          }
                        >
                          <Trash2 className="size-3" />
                        </Button>
                      </div>
                      {custom && (
                        <div className="mt-3 space-y-2">
                          <Textarea
                            aria-label="Custom section text"
                            rows={4}
                            value={custom.text}
                            onChange={(e) =>
                              patch({
                                custom_sections: config.custom_sections.map((s) =>
                                  s.id === key ? { ...s, text: e.target.value } : s,
                                ),
                              })
                            }
                          />
                        </div>
                      )}
                      <label className="mt-3 flex gap-2 text-xs">
                        <input
                          type="checkbox"
                          checked={custom?.page_break || config.page_breaks.includes(key)}
                          onChange={(e) =>
                            patch({
                              page_breaks: e.target.checked
                                ? [...config.page_breaks, key]
                                : config.page_breaks.filter((s) => s !== key),
                              custom_sections: config.custom_sections.map((s) =>
                                s.id === key ? { ...s, page_break: false } : s,
                              ),
                            })
                          }
                        />
                        Start on a new page
                      </label>
                    </div>
                  );
                })}
                <Field label="Add a report section">
                  <Select
                    value=""
                    onChange={(e) => {
                      if (e.target.value) patch({ sections: [...config.sections, e.target.value] });
                    }}
                  >
                    <option value="">Choose section…</option>
                    {Object.entries(SECTION_NAMES)
                      .filter(([key]) => !config.sections.includes(key))
                      .map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                  </Select>
                </Field>
                <Button
                  onClick={() => {
                    const id = `custom_${uid()}`;
                    patch({
                      sections: [...config.sections, id],
                      custom_sections: [
                        ...config.custom_sections,
                        { id, title: "Custom section", text: "", page_break: false },
                      ],
                    });
                  }}
                >
                  <Plus className="size-4" />
                  Add custom text section
                </Button>
              </div>
              <div className="border-t border-line pt-4 lg:col-span-2">
                <h4 className="mb-3 text-sm font-semibold">Default report scope</h4>
                <ScopeFields value={config.filters} onChange={(filters) => patch({ filters })} />
              </div>
            </div>
          )}
          {tab === "layout" && (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Page size">
                <Select
                  value={config.layout.page_size}
                  onChange={(e) => patchLayout({ page_size: e.target.value as "A4" | "Letter" })}
                >
                  <option>A4</option>
                  <option>Letter</option>
                </Select>
              </Field>
              <Field label="Orientation">
                <Select
                  value={config.layout.orientation}
                  onChange={(e) => patchLayout({ orientation: e.target.value as "portrait" | "landscape" })}
                >
                  <option value="portrait">Portrait</option>
                  <option value="landscape">Landscape</option>
                </Select>
              </Field>
              <Field label="Body font">
                <Select
                  value={config.layout.font}
                  onChange={(e) => patchLayout({ font: e.target.value as ReportLayout["font"] })}
                >
                  <option value="sans-serif">Sans serif</option>
                  <option value="serif">Serif</option>
                  <option value="monospace">Monospace</option>
                </Select>
              </Field>
              <NumberField
                label="Body size (pt)"
                value={config.layout.font_size}
                min={8}
                max={18}
                onChange={(font_size) => patchLayout({ font_size })}
              />
              <NumberField
                label="Body margin (mm)"
                value={config.layout.margin_mm}
                min={10}
                max={35}
                onChange={(margin_mm) => patchLayout({ margin_mm })}
              />
              <div className="space-y-4 pt-5">
                <label className="flex gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={config.layout.page_numbers}
                    onChange={(e) => patchLayout({ page_numbers: e.target.checked })}
                  />
                  Page numbers
                </label>
                <label className="flex gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={config.layout.show_cover}
                    onChange={(e) => patchLayout({ show_cover: e.target.checked })}
                  />
                  Include opening pages / cover
                </label>
              </div>
            </div>
          )}
        </div>
      </Dialog>
      {(preview || previewPdf) && (
        <Dialog
          open
          title="Report preview"
          description="Generated with your current settings and only the data you can access."
          onOpenChange={(o) => {
            if (!o) closePreview();
          }}
          className="max-w-[1120px]"
          footer={<Button onClick={closePreview}>Back to editor</Button>}
        >
          <iframe
            title="Generated report preview"
            srcDoc={preview ?? undefined}
            src={previewPdf ?? undefined}
            sandbox={previewPdf ? undefined : ""}
            className="h-[65vh] w-full rounded border border-line bg-white"
          />
        </Dialog>
      )}
    </>
  );
}
