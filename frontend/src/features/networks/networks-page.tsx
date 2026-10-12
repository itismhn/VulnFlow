import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { FileUp, MoreHorizontal, Network as NetworkIcon, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { SeverityCounters, SeverityStrip } from "@/components/severity";
import { Dialog, DropdownMenu, MenuItem } from "@/components/ui/overlay";
import {
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Select,
  Skeleton,
  Textarea,
} from "@/components/ui/primitives";
import { CriticalityDots } from "@/features/assets/assets-page";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useNetworks } from "@/lib/queries";
import type { Network, NetworkStats } from "@/lib/types";
import { cn, countsTotal, fmtNum } from "@/lib/utils";
import { AddressHeatmap } from "./address-heatmap";

export function NetworksPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const { data: networks = [], isLoading } = useNetworks();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Partial<Network> | null>(null);
  const [importing, setImporting] = useState(false);
  const [deleting, setDeleting] = useState<NetworkStats | null>(null);
  const selected = networks.find((n) => n.id === selectedId) ?? networks[0];
  const manage = can("networks:manage");

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["networks"] });
    qc.invalidateQueries({ queryKey: ["assets"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/networks/${id}`),
    onSuccess: () => {
      invalidate();
      setDeleting(null);
      setSelectedId(null);
      toast.success("Network deleted");
    },
  });

  return (
    <div className="animate-in">
      <PageHeader
        title="Networks"
        description="Name your IP ranges and zones. Assets join the most specific range that contains them, and every view can be filtered by range."
        actions={
          manage && (
            <>
              <Button onClick={() => setImporting(true)}>
                <FileUp className="size-4" /> Import CSV
              </Button>
              <Button variant="primary" onClick={() => setEditing({ criticality: 3 })}>
                <Plus className="size-4" /> Add network
              </Button>
            </>
          )
        }
      />

      {isLoading ? (
        <Skeleton className="h-96" />
      ) : !networks.length ? (
        <Card>
          <EmptyState
            icon={<NetworkIcon className="size-8" />}
            title="Define your first IP range"
            action={
              manage && (
                <Button variant="primary" onClick={() => setEditing({ criticality: 3 })}>
                  <Plus className="size-4" /> Add network
                </Button>
              )
            }
          >
            For example “Core Banking — 10.10.0.0/16”. Ranges drive filtering, scoped user access, the network
            report, and this address map.
          </EmptyState>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
          <Card className="overflow-hidden lg:sticky lg:top-20 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto">
            <ul className="divide-y divide-line">
              {networks.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(n.id)}
                    className={cn(
                      "w-full px-4 py-3 text-left transition hover:bg-surface-2/60",
                      selected?.id === n.id && "bg-brand-soft/50 shadow-[inset_3px_0_0_var(--brand)]",
                    )}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate font-medium">{n.name}</span>
                      <span className="shrink-0 font-mono text-xs text-ink-3">{n.cidr}</span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-ink-3">
                      {n.zone || "No zone"} · {fmtNum(n.asset_count)} assets
                      <span className="ml-auto">
                        <CriticalityDots value={n.criticality} />
                      </span>
                    </div>
                    <SeverityStrip counts={n.open} className="mt-2" />
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          {selected && (
            <Card className="p-5">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-display text-xl font-semibold">{selected.name}</h2>
                  <p className="mt-0.5 text-sm text-ink-2">
                    <span className="font-mono">{selected.cidr}</span>
                    {selected.zone && ` · ${selected.zone}`}
                    {selected.owner && ` · owned by ${selected.owner}`}
                  </p>
                  {selected.description && (
                    <p className="mt-2 max-w-2xl text-sm text-ink-2">{selected.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Link to="/findings" search={{ network_id: [selected.id] }}>
                    <Button variant="primary">{fmtNum(countsTotal(selected.open))} open findings</Button>
                  </Link>
                  {manage && (
                    <DropdownMenu
                      trigger={
                        <Button size="icon" aria-label="Network actions">
                          <MoreHorizontal className="size-4" />
                        </Button>
                      }
                    >
                      <MenuItem onSelect={() => setEditing(selected)}>
                        <Pencil className="size-4" /> Edit
                      </MenuItem>
                      <MenuItem danger onSelect={() => setDeleting(selected)}>
                        <Trash2 className="size-4" /> Delete
                      </MenuItem>
                    </DropdownMenu>
                  )}
                </div>
              </div>
              <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat label="Assets" value={fmtNum(selected.asset_count)} />
                <Stat label="Criticality" value={<CriticalityDots value={selected.criticality} />} />
                <div className="col-span-2 rounded-md border border-line px-3 py-2">
                  <div className="text-[11px] text-ink-3">Open by severity (C / H / M / L)</div>
                  <SeverityCounters counts={selected.open} className="mt-1 text-sm" />
                </div>
              </div>
              <AddressHeatmap key={selected.id} networkId={selected.id} cidr={selected.cidr} />
            </Card>
          )}
        </div>
      )}

      {editing && (
        <NetworkDialog
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={(n) => {
            invalidate();
            setSelectedId(n.id);
            setEditing(null);
          }}
        />
      )}
      <ImportDialog open={importing} onOpenChange={setImporting} onDone={invalidate} />
      <Dialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete ${deleting?.name}?`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => deleting && remove.mutate(deleting.id)}
            >
              Delete network
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink-2">
          Assets and findings are kept. Assets in this range move to the next-most-specific range, or become
          unassigned. Users scoped to this network lose access to it.
        </p>
      </Dialog>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-line px-3 py-2">
      <div className="text-[11px] text-ink-3">{label}</div>
      <div className="num mt-1 font-mono text-sm">{value}</div>
    </div>
  );
}

function NetworkDialog({
  initial,
  onClose,
  onSaved,
}: {
  initial: Partial<Network>;
  onClose: () => void;
  onSaved: (n: Network) => void;
}) {
  const [form, setForm] = useState({
    name: initial.name ?? "",
    cidr: initial.cidr ?? "",
    zone: initial.zone ?? "",
    criticality: initial.criticality ?? 3,
    owner: initial.owner ?? "",
    description: initial.description ?? "",
  });
  const set =
    (k: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm((f) => ({ ...f, [k]: k === "criticality" ? Number(e.target.value) : e.target.value }));
  const save = useMutation({
    mutationFn: () =>
      initial.id ? api.patch<Network>(`/networks/${initial.id}`, form) : api.post<Network>("/networks", form),
    onSuccess: (n) => {
      toast.success(initial.id ? "Network updated" : "Network added");
      onSaved(n);
    },
  });
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={initial.id ? "Edit network" : "Add network"}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={save.isPending}
            disabled={!form.name || !form.cidr}
            onClick={() => save.mutate()}
          >
            {initial.id ? "Save changes" : "Add network"}
          </Button>
        </>
      }
    >
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label="Name" className="sm:col-span-2">
          <Input value={form.name} onChange={set("name")} placeholder="Core Banking" autoFocus />
        </Field>
        <Field label="CIDR" hint="IPv4 or IPv6, e.g. 10.10.0.0/16">
          <Input value={form.cidr} onChange={set("cidr")} placeholder="10.10.0.0/16" className="font-mono" />
        </Field>
        <Field label="Zone" hint="Groups ranges, e.g. DMZ, PCI">
          <Input value={form.zone} onChange={set("zone")} placeholder="Core Banking" />
        </Field>
        <Field label="Criticality">
          <Select value={form.criticality} onChange={set("criticality")}>
            {[5, 4, 3, 2, 1].map((c) => (
              <option key={c} value={c}>
                {c} — {["", "Very low", "Low", "Moderate", "High", "Mission critical"][c]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Owner team">
          <Input value={form.owner} onChange={set("owner")} placeholder="Infrastructure" />
        </Field>
        <Field label="Description" className="sm:col-span-2">
          <Textarea value={form.description} onChange={set("description")} className="min-h-16" />
        </Field>
        <button type="submit" hidden />
      </form>
    </Dialog>
  );
}

function ImportDialog({
  open,
  onOpenChange,
  onDone,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onDone: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<{ created: number; updated: number; errors: string[] } | null>(null);
  const run = useMutation({
    mutationFn: () => {
      const form = new FormData();
      if (file) form.append("file", file);
      return api.upload<{ created: number; updated: number; errors: string[] }>("/networks/import", form);
    },
    onSuccess: (r) => {
      setResult(r);
      onDone();
    },
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) {
          setFile(null);
          setResult(null);
        }
      }}
      title="Import networks from CSV"
      description="Existing ranges with the same CIDR are updated."
      footer={
        result ? (
          <Button variant="primary" onClick={() => onOpenChange(false)}>
            Done
          </Button>
        ) : (
          <Button variant="primary" disabled={!file} loading={run.isPending} onClick={() => run.mutate()}>
            Import
          </Button>
        )
      }
    >
      {result ? (
        <div className="space-y-2 text-sm">
          <p>
            {result.created} created, {result.updated} updated.
          </p>
          {result.errors.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-critical">
              {result.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <pre className="rounded-md bg-surface-2 p-3 font-mono text-xs">
            name,cidr,zone,criticality,owner,description{"\n"}Core Banking,10.10.0.0/16,Core Banking,5,Infra,
            {"\n"}Internet DMZ,172.16.10.0/24,DMZ,4,Network team,
          </pre>
          <Input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="py-1.5"
          />
        </div>
      )}
    </Dialog>
  );
}
