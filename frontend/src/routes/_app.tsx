import { createFileRoute, Navigate } from "@tanstack/react-router";
import { ChangePasswordPage } from "@/features/auth/change-password";
import { AppShell } from "@/features/layout/shell";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/_app")({
  component: AppLayout,
});

function AppLayout() {
  const { me, loading } = useAuth();
  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center text-sm text-ink-3" aria-busy>
        Loading…
      </div>
    );
  }
  if (!me) return <Navigate to="/login" />;
  if (me.must_change_password) return <ChangePasswordPage forced />;
  return <AppShell />;
}
