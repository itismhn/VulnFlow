import { Link } from "@tanstack/react-router";
import { Lock, SearchX } from "lucide-react";
import type { ReactNode } from "react";
import { Button, Card, EmptyState } from "@/components/ui/primitives";
import { useAuth } from "@/lib/auth";

function BackHome() {
  return (
    <Link to="/">
      <Button variant="secondary">Back to dashboard</Button>
    </Link>
  );
}

/** Shown when a record does not exist or is outside the user's network scope. */
export function NotFound({ what }: { what: string }) {
  return (
    <Card>
      <EmptyState icon={<SearchX className="size-6" />} title={`${what} not found`} action={<BackHome />}>
        It may have been deleted, or it is outside the networks you have access to.
      </EmptyState>
    </Card>
  );
}

/** Page-level guard: renders children only when the user holds `perm`. */
export function RequirePerm({ perm, children }: { perm: string; children: ReactNode }) {
  const { can } = useAuth();
  if (can(perm)) return children;
  return (
    <Card>
      <EmptyState
        icon={<Lock className="size-6" />}
        title="You don't have access to this page"
        action={<BackHome />}
      >
        Ask an administrator if you need it.
      </EmptyState>
    </Card>
  );
}
