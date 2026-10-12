import * as Popover from "@radix-ui/react-popover";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { AtSign, Bell, ShieldAlert, ShieldCheck, ShieldX, UserPlus } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { AppNotification } from "@/lib/types";
import { cn, fmtRelative } from "@/lib/utils";

const ICONS: Record<AppNotification["kind"], ReactNode> = {
  mention: <AtSign />,
  assigned: <UserPlus />,
  risk_requested: <ShieldAlert />,
  risk_decided: <ShieldCheck />,
  risk_expired: <ShieldX />,
};

export function NotificationBell() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<{ items: AppNotification[]; unread: number }>("/notifications"),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
  const markRead = useMutation({
    mutationFn: (ids?: number[]) =>
      api.post(`/notifications/read${ids ? `?${ids.map((i) => `ids=${i}`).join("&")}` : ""}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const unread = data?.unread ?? 0;
  const items = data?.items ?? [];

  const open = (n: AppNotification) => {
    if (!n.read_at) markRead.mutate([n.id]);
    if (n.link) navigate({ href: n.link });
  };

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        >
          <Bell className="size-4" />
          {unread > 0 && (
            <span className="num absolute top-1 right-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-critical px-0.5 text-[9px] font-semibold text-white">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          className="animate-in z-50 w-[min(380px,calc(100vw-24px))] overflow-hidden rounded-lg border border-line bg-surface shadow-xl"
        >
          <div className="flex items-center justify-between border-b border-line px-3 py-2">
            <span className="font-display text-sm font-semibold">Notifications</span>
            {unread > 0 && (
              <button
                type="button"
                className="text-xs text-brand hover:underline"
                onClick={() => markRead.mutate(undefined)}
              >
                Mark all as read
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="px-4 py-10 text-center text-sm text-ink-3">
              Mentions, assignments, and approval decisions show up here.
            </p>
          ) : (
            <ul className="max-h-[60vh] divide-y divide-line overflow-y-auto">
              {items.map((n) => (
                <li key={n.id}>
                  <Popover.Close asChild>
                    <button
                      type="button"
                      onClick={() => open(n)}
                      className={cn(
                        "flex w-full gap-3 px-3 py-2.5 text-left transition hover:bg-surface-2",
                        !n.read_at && "bg-brand-soft/40",
                      )}
                    >
                      <span
                        className={cn(
                          "mt-0.5 shrink-0 [&_svg]:size-4",
                          n.kind === "risk_expired" ? "text-high" : "text-ink-3",
                        )}
                      >
                        {ICONS[n.kind]}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className={cn("block text-sm", !n.read_at && "font-medium")}>{n.title}</span>
                        {n.body && <span className="line-clamp-2 block text-xs text-ink-2">{n.body}</span>}
                        <span className="mt-0.5 block text-[11px] text-ink-3">
                          {n.actor ? `${n.actor.username} · ` : ""}
                          {fmtRelative(n.created_at)}
                        </span>
                      </span>
                      {!n.read_at && <span className="mt-1.5 size-2 shrink-0 rounded-full bg-brand" />}
                    </button>
                  </Popover.Close>
                </li>
              ))}
            </ul>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
