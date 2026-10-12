import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Command } from "cmdk";
import { Boxes, Bug, FileText, LayoutDashboard, ListChecks, Network, ScanLine, Upload } from "lucide-react";
import { type ReactNode, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useDebounced } from "@/lib/hooks";
import type { SearchHit } from "@/lib/types";

const itemCls =
  "flex cursor-default items-center gap-3 rounded-md px-3 py-2 text-sm text-ink data-[selected=true]:bg-surface-2 [&_svg]:size-4 [&_svg]:text-ink-3";

export function CommandPalette({
  open,
  onOpenChange,
  onUpload,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpload: () => void;
}) {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const term = useDebounced(q.trim(), 200);
  const { data: hits = [], isFetching } = useQuery({
    queryKey: ["search", term],
    queryFn: () => api.get<SearchHit[]>("/search", { q: term }),
    enabled: open && term.length >= 2,
  });

  function go(fn: () => void) {
    onOpenChange(false);
    setQ("");
    fn();
  }

  const jump = (to: string, label: string, icon: ReactNode) => (
    <Command.Item
      key={to}
      value={`go ${label}`}
      className={itemCls}
      onSelect={() => go(() => navigate({ to }))}
    >
      {icon}
      {label}
    </Command.Item>
  );

  const icons = { asset: <Boxes />, vulnerability: <Bug />, scan: <ScanLine /> };
  const openHit = (h: SearchHit) => {
    if (h.kind === "asset") navigate({ to: "/assets/$assetId", params: { assetId: String(h.id) } });
    else if (h.kind === "vulnerability")
      navigate({ to: "/vulnerabilities/$pluginId", params: { pluginId: String(h.id) } });
    else navigate({ to: "/scans/$scanId", params: { scanId: String(h.id) } });
  };

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <DialogPrimitive.Content className="animate-in fixed top-[12vh] left-1/2 z-50 w-[calc(100vw-32px)] max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border border-line bg-surface shadow-2xl">
          <DialogPrimitive.Title className="sr-only">Search</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            Search assets, vulnerabilities and scans
          </DialogPrimitive.Description>
          <Command shouldFilter={false} label="Search">
            <Command.Input
              value={q}
              onValueChange={setQ}
              placeholder="Search an IP, hostname, CVE, plugin ID or scan…"
              className="h-12 w-full border-b border-line bg-transparent px-4 text-sm outline-none placeholder:text-ink-3"
            />
            <Command.List className="max-h-[60vh] overflow-y-auto p-2">
              {term.length >= 2 && !isFetching && hits.length === 0 && (
                <Command.Empty className="px-3 py-6 text-center text-sm text-ink-3">
                  Nothing matches “{term}”.
                </Command.Empty>
              )}
              {hits.length > 0 && (
                <Command.Group
                  heading="Results"
                  className="text-[11px] text-ink-3 [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5"
                >
                  {hits.map((h) => (
                    <Command.Item
                      key={`${h.kind}-${h.id}`}
                      value={`${h.kind}-${h.id}`}
                      className={itemCls}
                      onSelect={() => go(() => openHit(h))}
                    >
                      {icons[h.kind]}
                      <span className={h.kind === "asset" ? "font-mono" : ""}>{h.title}</span>
                      <span className="ml-auto truncate text-xs text-ink-3">{h.subtitle}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
              {term.length < 2 && (
                <Command.Group
                  heading="Go to"
                  className="text-[11px] text-ink-3 [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5"
                >
                  {jump("/", "Dashboard", <LayoutDashboard />)}
                  {jump("/findings", "Findings", <ListChecks />)}
                  {jump("/vulnerabilities", "Vulnerabilities", <Bug />)}
                  {jump("/assets", "Assets", <Boxes />)}
                  {jump("/networks", "Networks", <Network />)}
                  {jump("/scans", "Scan history", <ScanLine />)}
                  {jump("/reports", "Reports", <FileText />)}
                  {can("scans:upload") && (
                    <Command.Item value="import scan" className={itemCls} onSelect={() => go(onUpload)}>
                      <Upload /> Import a .nessus file
                    </Command.Item>
                  )}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
