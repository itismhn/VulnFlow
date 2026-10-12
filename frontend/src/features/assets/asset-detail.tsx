import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ShieldCheck, ShieldOff, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { SeverityBadge, SeverityCounters, SeverityStrip, StatusBadge } from "@/components/severity";
import { NotFound } from "@/components/states";
import { Button, Card, CardHeader, Input, PageHeader, Select, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AssetRow, AssetScan, Finding, Page } from "@/lib/types";
import { fmtDate, fmtNum } from "@/lib/utils";
import { CriticalityDots } from "./assets-page";

export function AssetDetailPage({ id }: { id: number }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const { data: asset, isError } = useQuery({
    queryKey: ["assets", "detail", id],
    queryFn: () => api.get<AssetRow>(`/assets/${id}`),
  });
  const { data: scans = [] } = useQuery({
    queryKey: ["assets", "scans", id],
    queryFn: () => api.get<AssetScan[]>(`/assets/${id}/scans`),
  });
  const { data: findings } = useQuery({
    queryKey: ["findings", "list", { asset_id: id }],
    queryFn: () => api.get<Page<Finding>>("/findings", { asset_id: id, page_size: 200 }),
  });
  const [tag, setTag] = useState("");
  const update = useMutation({
    mutationFn: (body: { criticality?: number; clear_criticality?: boolean; tags?: string[] }) =>
      api.patch<AssetRow>(`/assets/${id}`, body),
    onSuccess: (a) => {
      qc.setQueryData(["assets", "detail", id], a);
      qc.invalidateQueries({ queryKey: ["assets"] });
      toast.success("Asset updated");
    },
  });

  if (isError) return <NotFound what="Asset" />;
  if (!asset) return <Skeleton className="h-64" />;
  const editable = can("assets:update");

  return (
    <div className="animate-in">
      <PageHeader
        eyebrow={
          <Link to="/assets" className="hover:text-ink">
            Assets
          </Link>
        }
        title={<span className="font-mono">{asset.ip}</span>}
        description={
          [asset.hostname, asset.fqdn, asset.os].filter(Boolean).join(" · ") || "No host details reported"
        }
        actions={
          <Link to="/findings" search={{ asset_id: id }}>
            <Button variant="primary">Open in findings</Button>
          </Link>
        }
      />

      <div className="mb-4 grid gap-4 lg:grid-cols-3">
        <Card className="p-4 lg:col-span-2">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="text-xs text-ink-3">Risk score</div>
              <div className="num font-display text-4xl font-semibold">{asset.risk_score}</div>
            </div>
            <SeverityCounters counts={asset.open} className="text-sm" />
          </div>
          <SeverityStrip counts={asset.open} className="mt-3" height="h-2" />
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-[11px] text-ink-3">Network</dt>
              <dd>{asset.network_name ?? "Unassigned"}</dd>
            </div>
            <div>
              <dt className="text-[11px] text-ink-3">Zone</dt>
              <dd>{asset.zone || "—"}</dd>
            </div>
            <div>
              <dt className="text-[11px] text-ink-3">First seen</dt>
              <dd>{fmtDate(asset.first_seen)}</dd>
            </div>
            <div>
              <dt className="text-[11px] text-ink-3">Last seen</dt>
              <dd>{fmtDate(asset.last_seen)}</dd>
            </div>
            {asset.netbios && (
              <div>
                <dt className="text-[11px] text-ink-3">NetBIOS</dt>
                <dd className="font-mono text-xs">{asset.netbios}</dd>
              </div>
            )}
            {asset.mac && (
              <div className="col-span-2">
                <dt className="text-[11px] text-ink-3">MAC</dt>
                <dd className="font-mono text-xs">{asset.mac}</dd>
              </div>
            )}
          </dl>
        </Card>

        <Card className="space-y-4 p-4">
          <div>
            <div className="mb-1.5 flex items-center justify-between text-xs text-ink-3">
              Business criticality <CriticalityDots value={asset.effective_criticality} />
            </div>
            {editable ? (
              <Select
                value={asset.criticality ?? ""}
                onChange={(e) =>
                  update.mutate(
                    e.target.value ? { criticality: Number(e.target.value) } : { clear_criticality: true },
                  )
                }
              >
                <option value="">Inherit from network ({asset.effective_criticality})</option>
                {[5, 4, 3, 2, 1].map((c) => (
                  <option key={c} value={c}>
                    {c} — {["", "Very low", "Low", "Moderate", "High", "Mission critical"][c]}
                  </option>
                ))}
              </Select>
            ) : (
              <p className="text-sm">{asset.effective_criticality} of 5</p>
            )}
          </div>
          <div>
            <div className="mb-1.5 text-xs text-ink-3">Tags</div>
            <div className="flex flex-wrap gap-1.5">
              {asset.tags.map((t) => (
                <span
                  key={t}
                  className="inline-flex items-center gap-1 rounded bg-surface-2 px-2 py-0.5 text-xs"
                >
                  {t}
                  {editable && (
                    <button
                      type="button"
                      aria-label={`Remove ${t}`}
                      onClick={() => update.mutate({ tags: asset.tags.filter((x) => x !== t) })}
                    >
                      <X className="size-3 text-ink-3 hover:text-ink" />
                    </button>
                  )}
                </span>
              ))}
              {!asset.tags.length && <span className="text-xs text-ink-3">No tags</span>}
            </div>
            {editable && (
              <form
                className="mt-2 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (tag.trim()) update.mutate({ tags: [...asset.tags, tag.trim()] });
                  setTag("");
                }}
              >
                <Input
                  value={tag}
                  onChange={(e) => setTag(e.target.value)}
                  placeholder="e.g. pci, swift, owner:payments"
                  className="h-8 text-xs"
                />
                <Button size="sm" type="submit">
                  Add
                </Button>
              </form>
            )}
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="overflow-hidden lg:col-span-2">
          <CardHeader
            title="Open findings"
            description={`${fmtNum(findings?.total ?? 0)} active on this host`}
          />
          <ul className="divide-y divide-line">
            {findings?.items.map((f) => (
              <li key={f.id}>
                <Link
                  to="/findings"
                  search={{ asset_id: id, finding: f.id }}
                  className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-2/60"
                >
                  <SeverityBadge severity={f.severity} />
                  <span className="min-w-0 flex-1 truncate text-sm">{f.plugin.name}</span>
                  <span className="font-mono text-xs text-ink-3">
                    {f.port}/{f.protocol}
                  </span>
                  <StatusBadge status={f.status} />
                </Link>
              </li>
            ))}
            {findings && !findings.items.length && (
              <li className="px-4 py-8 text-center text-sm text-ink-3">No open findings on this host.</li>
            )}
          </ul>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader title="Scan timeline" description="Every scan that covered this host" />
          <ol className="divide-y divide-line">
            {scans.map((s) => (
              <li key={s.scan_id} className="px-4 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <Link
                    to="/scans/$scanId"
                    params={{ scanId: String(s.scan_id) }}
                    className="truncate text-sm hover:text-brand"
                  >
                    {s.scan_name}
                  </Link>
                  {s.credentialed ? (
                    <ShieldCheck className="size-3.5 shrink-0 text-ok" aria-label="Credentialed" />
                  ) : (
                    <ShieldOff className="size-3.5 shrink-0 text-ink-3" aria-label="Uncredentialed" />
                  )}
                </div>
                <div className="mt-1 flex items-center justify-between gap-2">
                  <span className="text-xs text-ink-3">{fmtDate(s.started_at)}</span>
                  <SeverityCounters counts={s.findings} />
                </div>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}
