import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { SeverityLegend, severityBg } from "@/components/severity";
import { Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn, severityLabel } from "@/lib/utils";

interface MapCell {
  address: string;
  asset_id: number | null;
  label: string;
  hosts: number;
  max_severity: number;
}
interface NetworkMap {
  mode: "host" | "block";
  cidr: string;
  cells: MapCell[];
}

const ipToInt = (ip: string) => ip.split(".").reduce((acc, o) => acc * 256 + Number(o), 0);
const intToIp = (n: number) => [24, 16, 8, 0].map((s) => Math.floor(n / 2 ** s) % 256).join(".");

function cellClass(sev: number | undefined) {
  if (sev === undefined) return "bg-none/50";
  if (sev < 0) return "border border-ink-3/70 bg-surface";
  return severityBg(sev);
}

/**
 * The address-space heatmap: one cell per address (or per /24 for large ranges),
 * coloured by the worst open severity. Unscanned addresses stay faint, so
 * coverage gaps are as visible as risk.
 */
export function AddressHeatmap({ networkId, cidr }: { networkId: number; cidr: string }) {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["networks", "map", networkId],
    queryFn: () => api.get<NetworkMap>(`/networks/${networkId}/map`),
  });

  const grid = useMemo(() => {
    if (!data) return null;
    const [base, prefixStr] = data.cidr.split("/");
    const prefix = Number(prefixStr);
    const isV4 = !base.includes(":");
    if (data.mode === "host" && isV4) {
      const size = 2 ** (32 - prefix);
      const start = ipToInt(base);
      const byAddr = new Map(data.cells.map((c) => [c.address, c]));
      const cells = Array.from({ length: size }, (_, i) => {
        const address = intToIp(start + i);
        return { address, cell: byAddr.get(address) };
      });
      return {
        cells,
        cols:
          size >= 1024 ? 64 : size >= 512 ? 32 : size >= 64 ? 16 : Math.max(4, Math.ceil(Math.sqrt(size))),
      };
    }
    if (data.mode === "block" && isV4 && prefix >= 14) {
      const blocks = 2 ** (24 - prefix);
      const start = ipToInt(base);
      const byAddr = new Map(data.cells.map((c) => [c.address, c]));
      const cells = Array.from({ length: blocks }, (_, i) => {
        const address = `${intToIp(start + i * 256)}/24`;
        return { address, cell: byAddr.get(address) };
      });
      return { cells, cols: Math.min(32, blocks) };
    }
    return {
      cells: data.cells.map((c) => ({ address: c.address, cell: c as MapCell | undefined })),
      cols: 16,
    };
  }, [data]);

  if (isLoading || !grid || !data) return <Skeleton className="aspect-[2/1] w-full" />;

  const scanned = data.cells.length;
  const withFindings = data.cells.filter((c) => c.max_severity > 0).length;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-ink-2">
          {data.mode === "host"
            ? `${scanned} of ${grid.cells.length} addresses seen in scans · ${withFindings} with open findings`
            : `${scanned} /24 blocks with assets · one cell per /24`}
        </p>
        <SeverityLegend withNone />
      </div>
      <div
        className="grid gap-[3px]"
        style={{ gridTemplateColumns: `repeat(${grid.cols}, minmax(0, 1fr))`, maxWidth: grid.cols * 30 }}
        role="grid"
        aria-label={`Address map of ${cidr}`}
      >
        {grid.cells.map(({ address, cell }) => {
          const sev = cell?.max_severity;
          const tip = cell
            ? `${address}${cell.label ? ` · ${cell.label}` : ""}${data.mode === "block" ? ` · ${cell.hosts} hosts` : ""} · ${
                sev !== undefined && sev > 0 ? `worst: ${severityLabel(sev)}` : "no open findings"
              }`
            : `${address} · not seen in any scan`;
          const clickable = !!cell;
          const onClick = () => {
            if (!cell) return;
            if (cell.asset_id)
              navigate({ to: "/assets/$assetId", params: { assetId: String(cell.asset_id) } });
            else navigate({ to: "/findings", search: { ip: address, group: "host" } });
          };
          return (
            <button
              key={address}
              type="button"
              title={tip}
              aria-label={tip}
              disabled={!clickable}
              onClick={onClick}
              className={cn(
                "aspect-square rounded-[2px] transition",
                cellClass(sev),
                clickable && "hover:scale-125 hover:ring-2 hover:ring-ink/30 focus-visible:scale-125",
              )}
            />
          );
        })}
      </div>
    </div>
  );
}
