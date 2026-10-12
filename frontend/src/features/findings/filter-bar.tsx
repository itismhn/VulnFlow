import * as Popover from "@radix-ui/react-popover";
import { ChevronDown, Flame, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useState } from "react";
import { severityBg } from "@/components/severity";
import { DropdownMenu, MenuLabel } from "@/components/ui/overlay";
import { Button, Field, Input, Select } from "@/components/ui/primitives";
import { useDebounced } from "@/lib/hooks";
import { useNetworks, useZones } from "@/lib/queries";
import type { FindingsSearch } from "@/lib/search";
import type { FindingStatus } from "@/lib/types";
import { ACTIVE_STATUSES, cn, SEVERITIES, STATUS_LABELS } from "@/lib/utils";

type Patch = (p: Partial<FindingsSearch>) => void;

function toggle<T>(list: T[] | undefined, v: T): T[] | undefined {
  const set = new Set(list ?? []);
  if (set.has(v)) set.delete(v);
  else set.add(v);
  return set.size ? [...set] : undefined;
}

export function FilterBar({ search, patch }: { search: FindingsSearch; patch: Patch }) {
  const [q, setQ] = useState(search.q ?? "");
  const [ip, setIp] = useState(search.ip ?? "");
  const dq = useDebounced(q, 350);
  const dip = useDebounced(ip, 500);
  const { data: networks = [] } = useNetworks();
  const { data: zones = [] } = useZones();

  // biome-ignore lint/correctness/useExhaustiveDependencies: sync debounced inputs only
  useEffect(() => {
    if ((dq || undefined) !== search.q) patch({ q: dq || undefined });
  }, [dq]);
  // biome-ignore lint/correctness/useExhaustiveDependencies: sync debounced inputs only
  useEffect(() => {
    if ((dip || undefined) !== search.ip) patch({ ip: dip || undefined });
  }, [dip]);
  useEffect(() => setQ(search.q ?? ""), [search.q]);
  useEffect(() => setIp(search.ip ?? ""), [search.ip]);

  const statuses = search.status ?? ACTIVE_STATUSES;
  const statusLabel =
    !search.status || search.status.length === 0
      ? "Active"
      : search.status.length === 1
        ? STATUS_LABELS[search.status[0]]
        : `${search.status.length} statuses`;

  const moreCount = [
    search.cve,
    search.port,
    search.family,
    search.overdue,
    search.include_info,
    search.scan_id,
    search.min_cvss,
    search.zone,
  ].filter((v) => v !== undefined).length;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-56 flex-1">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-ink-3" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search vulnerability, host, CVE, plugin ID…"
          className="pl-8"
          aria-label="Search findings"
        />
      </div>

      <Input
        value={ip}
        onChange={(e) => setIp(e.target.value)}
        placeholder="IP or CIDR, e.g. 10.10.0.0/24"
        className="w-56 font-mono text-xs"
        aria-label="IP address or range"
      />

      <div
        className="flex h-9 items-center rounded-md border border-line bg-surface p-0.5"
        role="group"
        aria-label="Severity"
      >
        {SEVERITIES.filter((s) => s.value > 0).map((s) => {
          const on = search.severity?.includes(s.value);
          return (
            <button
              key={s.value}
              type="button"
              aria-pressed={!!on}
              onClick={() => patch({ severity: toggle(search.severity, s.value) })}
              className={cn(
                "flex h-full items-center gap-1.5 rounded px-2.5 text-xs font-medium transition",
                on ? "bg-surface-2 text-ink shadow-sm" : "text-ink-3 hover:text-ink",
              )}
            >
              <span className={cn("size-2 rounded-full", severityBg(s.value))} />
              {s.label}
            </button>
          );
        })}
      </div>

      <DropdownMenu
        align="start"
        trigger={
          <Button>
            {statusLabel}
            <ChevronDown className="size-3.5 text-ink-3" />
          </Button>
        }
      >
        <MenuLabel>Status</MenuLabel>
        {(Object.keys(STATUS_LABELS) as FindingStatus[]).map((s) => (
          <label
            key={s}
            className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-sm hover:bg-surface-2"
          >
            <input
              type="checkbox"
              className="accent-[var(--brand)]"
              checked={statuses.includes(s)}
              onChange={() => {
                const next = toggle(statuses, s);
                const isDefault =
                  next?.length === ACTIVE_STATUSES.length && ACTIVE_STATUSES.every((a) => next.includes(a));
                patch({ status: isDefault ? undefined : (next ?? ["open"]) });
              }}
            />
            {STATUS_LABELS[s]}
          </label>
        ))}
      </DropdownMenu>

      <Select
        value={search.network_id?.[0] ?? ""}
        onChange={(e) => patch({ network_id: e.target.value ? [Number(e.target.value)] : undefined })}
        className="w-48"
        aria-label="Network"
      >
        <option value="">All networks</option>
        {networks.map((n) => (
          <option key={n.id} value={n.id}>
            {n.name} ({n.cidr})
          </option>
        ))}
      </Select>

      <Button
        aria-pressed={!!search.exploitable}
        onClick={() => patch({ exploitable: search.exploitable ? undefined : true })}
        className={cn(search.exploitable && "border-critical/40 bg-critical/8 text-critical")}
      >
        <Flame className="size-3.5" /> Exploitable
      </Button>

      <Popover.Root>
        <Popover.Trigger asChild>
          <Button>
            <SlidersHorizontal className="size-3.5" /> More{moreCount ? ` (${moreCount})` : ""}
          </Button>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            align="end"
            sideOffset={6}
            className="animate-in z-50 w-80 space-y-3 rounded-lg border border-line bg-surface p-4 shadow-xl"
          >
            <Field label="Zone">
              <Select
                value={search.zone?.[0] ?? ""}
                onChange={(e) => patch({ zone: e.target.value ? [e.target.value] : undefined })}
              >
                <option value="">Any zone</option>
                {zones.map((z) => (
                  <option key={z}>{z}</option>
                ))}
              </Select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="CVE">
                <Input
                  defaultValue={search.cve}
                  placeholder="CVE-2024-…"
                  onBlur={(e) => patch({ cve: e.target.value.trim() || undefined })}
                />
              </Field>
              <Field label="Port">
                <Input
                  type="number"
                  defaultValue={search.port}
                  onBlur={(e) => patch({ port: e.target.value ? Number(e.target.value) : undefined })}
                />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Min. CVSS">
                <Input
                  type="number"
                  step="0.1"
                  min={0}
                  max={10}
                  defaultValue={search.min_cvss}
                  onBlur={(e) => patch({ min_cvss: e.target.value ? Number(e.target.value) : undefined })}
                />
              </Field>
              <Field label="Plugin family">
                <Input
                  defaultValue={search.family}
                  onBlur={(e) => patch({ family: e.target.value.trim() || undefined })}
                />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="accent-[var(--brand)]"
                checked={!!search.overdue}
                onChange={(e) => patch({ overdue: e.target.checked || undefined })}
              />
              Past due date only
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="accent-[var(--brand)]"
                checked={!!search.include_info}
                onChange={(e) => patch({ include_info: e.target.checked || undefined })}
              />
              Include informational findings
            </label>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </div>
  );
}

/** Removable chips for filters that aren't visible in the bar itself. */
export function ActiveFilterChips({
  search,
  patch,
  onClear,
}: {
  search: FindingsSearch;
  patch: Patch;
  onClear: () => void;
}) {
  const chips: { label: string; clear: Partial<FindingsSearch> }[] = [];
  if (search.asset_id) chips.push({ label: `Asset #${search.asset_id}`, clear: { asset_id: undefined } });
  if (search.plugin_id)
    chips.push({ label: `Plugin ${search.plugin_id.join(", ")}`, clear: { plugin_id: undefined } });
  if (search.scan_id) chips.push({ label: `Seen in scan #${search.scan_id}`, clear: { scan_id: undefined } });
  if (search.zone) chips.push({ label: `Zone: ${search.zone.join(", ")}`, clear: { zone: undefined } });
  if (search.cve) chips.push({ label: search.cve, clear: { cve: undefined } });
  if (search.port !== undefined) chips.push({ label: `Port ${search.port}`, clear: { port: undefined } });
  if (search.family) chips.push({ label: search.family, clear: { family: undefined } });
  if (search.min_cvss !== undefined)
    chips.push({ label: `CVSS ≥ ${search.min_cvss}`, clear: { min_cvss: undefined } });
  if (search.overdue) chips.push({ label: "Overdue", clear: { overdue: undefined } });
  if (search.assignee_id) chips.push({ label: "Assigned to me", clear: { assignee_id: undefined } });
  if (search.include_info) chips.push({ label: "Including info", clear: { include_info: undefined } });

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {chips.map((c) => (
        <button
          key={c.label}
          type="button"
          onClick={() => patch(c.clear)}
          className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs text-ink-2 hover:border-ink-3/50"
        >
          {c.label}
          <X className="size-3" />
        </button>
      ))}
      <button type="button" onClick={onClear} className="px-1 text-xs text-ink-3 hover:text-ink">
        Clear all filters
      </button>
    </div>
  );
}
