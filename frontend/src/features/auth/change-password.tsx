import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { HeatmapMark } from "@/components/brand";
import { Button, Card, Field, Input } from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Me } from "@/lib/types";

const RULES = [
  { test: (p: string) => p.length >= 12, label: "12+ characters" },
  { test: (p: string) => /[a-z]/.test(p), label: "lowercase letter" },
  { test: (p: string) => /[A-Z]/.test(p), label: "uppercase letter" },
  { test: (p: string) => /\d/.test(p), label: "digit" },
  { test: (p: string) => /[^a-zA-Z0-9]/.test(p), label: "symbol" },
];

export function ChangePasswordForm({ onDone }: { onDone?: () => void }) {
  const qc = useQueryClient();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const valid = RULES.every((r) => r.test(next)) && next === confirm;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api.post<Me>("/auth/change-password", {
        current_password: current,
        new_password: next,
      });
      qc.setQueryData(["me"], me);
      toast.success("Password changed");
      setCurrent("");
      setNext("");
      setConfirm("");
      onDone?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't change the password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Current password">
        <Input
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          required
        />
      </Field>
      <Field label="New password">
        <Input
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          required
        />
      </Field>
      <ul className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        {RULES.map((r) => (
          <li key={r.label} className={r.test(next) ? "text-ok" : "text-ink-3"}>
            {r.test(next) ? "✓" : "○"} {r.label}
          </li>
        ))}
      </ul>
      <Field
        label="Confirm new password"
        error={confirm && next !== confirm ? "Passwords don't match" : null}
      >
        <Input
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
        />
      </Field>
      {error && <p className="text-sm text-critical">{error}</p>}
      <Button type="submit" variant="primary" disabled={!valid} loading={busy}>
        Change password
      </Button>
    </form>
  );
}

export function ChangePasswordPage({ forced }: { forced?: boolean }) {
  const { logout } = useAuth();
  return (
    <div className="grid min-h-screen place-items-center p-6">
      <Card className="w-full max-w-md p-6">
        <HeatmapMark className="mb-4 size-7" />
        <h1 className="font-display text-xl font-semibold">Set a new password</h1>
        <p className="mt-1 mb-5 text-sm text-ink-2">
          {forced
            ? "Your password was set by an administrator. Choose your own before continuing."
            : "Choose a strong password you don't use anywhere else."}
        </p>
        <ChangePasswordForm />
        <button type="button" onClick={logout} className="mt-4 text-xs text-ink-3 hover:text-ink">
          Sign out instead
        </button>
      </Card>
    </div>
  );
}
