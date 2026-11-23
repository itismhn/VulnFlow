import { Field, Input, Select } from "@/components/ui/primitives";
import { useNetworks, useZones } from "@/lib/queries";
import type { FindingFilters, FindingStatus } from "@/lib/types";
import { cn, SEVERITIES, STATUS_LABELS } from "@/lib/utils";

export function ScopeFields({
  value,
  onChange,
}: {
  value: FindingFilters;
  onChange: (f: FindingFilters) => void;
}) {
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
