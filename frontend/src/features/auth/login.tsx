import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { HeatmapMark } from "@/components/brand";
import { Button, Field, Input } from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { Me } from "@/lib/types";

export function LoginPage() {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api.post<Me>("/auth/login", { username, password });
      qc.setQueryData(["me"], me);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Can't reach the server. Check your connection.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-[#0e1a2b] p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-2.5">
          <HeatmapMark className="size-7" />
          <span className="font-display text-lg font-semibold tracking-tight">Report Manager</span>
        </div>
        <div className="max-w-md space-y-10">
          <div>
            <h1 className="font-display text-4xl leading-tight font-semibold tracking-tight">
              Every scan, every host, every fix — in one place.
            </h1>
            <p className="mt-4 text-[15px] text-slate-300">
              Import Nessus results, track each vulnerability from first detection to verified fix, and report
              by network range or severity.
            </p>
          </div>
          <LoginGrid />
        </div>
        <p className="relative z-10 text-xs text-slate-500">
          Self-hosted · Your scan data never leaves your network
        </p>
      </aside>

      <main className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5">
          <div className="lg:hidden flex items-center gap-2">
            <HeatmapMark className="size-6" />
            <span className="font-display font-semibold">Report Manager</span>
          </div>
          <div>
            <h2 className="font-display text-2xl font-semibold tracking-tight">Sign in</h2>
            <p className="mt-1 text-sm text-ink-2">Use the account your administrator created for you.</p>
          </div>
          <Field label="Username">
            <Input
              autoFocus
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </Field>
          <Field label="Password">
            <Input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Field>
          {error && (
            <p
              role="alert"
              className="rounded-md border border-critical/30 bg-critical/8 px-3 py-2 text-sm text-critical"
            >
              {error}
            </p>
          )}
          <Button type="submit" variant="primary" className="w-full justify-center" loading={busy}>
            Sign in
          </Button>
          <p className="text-xs text-ink-3">
            Forgot your password? Ask an administrator to reset it. Accounts lock for 15 minutes after
            repeated failed attempts.
          </p>
        </form>
      </main>
    </div>
  );
}

/** Decorative address-space grid on the sign-in panel (deterministic, no data). */
function LoginGrid() {
  const palette = ["#b91c1c", "#c2410c", "#ca8a04", "#2563eb"];
  const cells = Array.from({ length: 16 * 6 }, (_, i) => {
    const r = (Math.sin(i * 12.9898) * 43758.5453) % 1;
    const v = Math.abs(r);
    if (v > 0.93) return palette[0];
    if (v > 0.86) return palette[1];
    if (v > 0.74) return palette[2];
    if (v > 0.62) return palette[3];
    if (v > 0.3) return "#1c2b42";
    return "transparent";
  });
  return (
    <div
      aria-hidden
      className="pointer-events-none grid gap-1.5 opacity-70"
      style={{ gridTemplateColumns: "repeat(16, 14px)" }}
    >
      {cells.map((c, i) => (
        <span
          key={i}
          className="size-[14px] rounded-[3px]"
          style={{ background: c, border: c === "transparent" ? "1px solid #1c2b42" : undefined }}
        />
      ))}
    </div>
  );
}
