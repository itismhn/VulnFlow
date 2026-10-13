import { Link, Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  BadgeCheck,
  Boxes,
  Bug,
  ClipboardList,
  FileText,
  Gauge,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Moon,
  Network,
  PackageSearch,
  ScanLine,
  ScrollText,
  Search,
  Settings,
  Sun,
  Upload,
  UserRound,
  Users,
} from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { HeatmapMark } from "@/components/brand";
import { DropdownMenu, MenuItem, MenuLabel, MenuSeparator } from "@/components/ui/overlay";
import { Button, Kbd } from "@/components/ui/primitives";
import { CommandPalette } from "@/features/layout/command-palette";
import { UploadDialog } from "@/features/scans/upload-dialog";
import { NotificationBell } from "@/features/workflow/notification-bell";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  perm?: string;
}

const NAV: { title: string; items: NavItem[] }[] = [
  {
    title: "Overview",
    items: [
      { to: "/", label: "Dashboard", icon: <LayoutDashboard /> },
      { to: "/metrics", label: "Remediation metrics", icon: <Gauge /> },
    ],
  },
  {
    title: "Vulnerability management",
    items: [
      { to: "/my-work", label: "My work", icon: <ClipboardList />, perm: "findings:update" },
      { to: "/findings", label: "Findings", icon: <ListChecks /> },
      { to: "/approvals", label: "Risk approvals", icon: <BadgeCheck /> },
      { to: "/vulnerabilities", label: "Vulnerabilities", icon: <Bug /> },
      { to: "/assets", label: "Assets", icon: <Boxes /> },
      { to: "/software", label: "Software", icon: <PackageSearch /> },
      { to: "/networks", label: "Networks", icon: <Network /> },
    ],
  },
  {
    title: "Scans & reports",
    items: [
      { to: "/scans", label: "Scan history", icon: <ScanLine /> },
      { to: "/reports", label: "Reports", icon: <FileText /> },
    ],
  },
  {
    title: "Administration",
    items: [
      { to: "/admin/users", label: "Users", icon: <Users />, perm: "users:manage" },
      { to: "/admin/audit", label: "Audit log", icon: <ScrollText />, perm: "audit:read" },
      { to: "/admin/settings", label: "Settings", icon: <Settings />, perm: "settings:manage" },
    ],
  },
];

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { can } = useAuth();
  const path = useRouterState({ select: (s) => s.location.pathname });
  return (
    <nav className="flex h-full flex-col gap-5 overflow-y-auto px-3 py-4" aria-label="Main">
      <Link to="/" className="flex items-center gap-2.5 px-2" onClick={onNavigate}>
        <HeatmapMark className="size-7" />
        <div className="leading-tight">
          <div className="font-display text-[15px] font-semibold tracking-tight">Report Manager</div>
          <div className="text-[11px] text-ink-3">Vulnerability management</div>
        </div>
      </Link>
      {NAV.map((group) => {
        const items = group.items.filter((i) => !i.perm || can(i.perm));
        if (!items.length) return null;
        return (
          <div key={group.title}>
            <div className="mb-1 px-2 text-[11px] font-medium text-ink-3">{group.title}</div>
            <ul className="space-y-0.5">
              {items.map((item) => {
                const active = item.to === "/" ? path === "/" : path.startsWith(item.to);
                return (
                  <li key={item.to}>
                    <Link
                      to={item.to}
                      onClick={onNavigate}
                      className={cn(
                        "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition [&_svg]:size-4",
                        active
                          ? "bg-brand-soft font-medium text-brand"
                          : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                      )}
                    >
                      {item.icon}
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

export function AppShell() {
  const { me, can, logout } = useAuth();
  const [theme, toggleTheme] = useTheme();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 border-r border-line bg-surface lg:block">
        <Sidebar />
      </aside>
      {mobileNav && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-black/40"
            onClick={() => setMobileNav(false)}
          />
          <aside className="slide-in absolute inset-y-0 left-0 w-64 border-r border-line bg-surface">
            <Sidebar onNavigate={() => setMobileNav(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-line bg-bg/85 px-4 backdrop-blur lg:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Open menu"
            onClick={() => setMobileNav(true)}
          >
            <Menu className="size-4" />
          </Button>
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="flex h-9 w-full max-w-md items-center gap-2 rounded-md border border-line bg-surface px-3 text-sm text-ink-3 transition hover:border-ink-3/40"
          >
            <Search className="size-4" />
            <span className="flex-1 text-left">Search IPs, hosts, CVEs, plugins…</span>
            <Kbd>⌘K</Kbd>
          </button>
          <div className="ml-auto flex items-center gap-1.5">
            {can("scans:upload") && (
              <Button variant="primary" onClick={() => setUploadOpen(true)}>
                <Upload className="size-4" />
                <span className="hidden sm:inline">Import scan</span>
              </Button>
            )}
            <NotificationBell />
            <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle colour theme">
              {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>
            <DropdownMenu
              trigger={
                <button
                  type="button"
                  className="flex size-8 items-center justify-center rounded-full bg-brand-soft font-display text-sm font-semibold text-brand uppercase"
                  aria-label="Account menu"
                >
                  {me?.username.slice(0, 1)}
                </button>
              }
            >
              <MenuLabel>
                {me?.full_name || me?.username} · {me?.role}
              </MenuLabel>
              <MenuSeparator />
              <MenuItem onSelect={() => navigate({ to: "/account" })}>
                <UserRound className="size-4" /> Account & password
              </MenuItem>
              <MenuItem onSelect={logout}>
                <LogOut className="size-4" /> Sign out
              </MenuItem>
            </DropdownMenu>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-6 lg:px-6">
          <Outlet />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} onUpload={() => setUploadOpen(true)} />
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </div>
  );
}
