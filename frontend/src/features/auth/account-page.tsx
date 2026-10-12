import { Badge, Card, CardHeader, PageHeader } from "@/components/ui/primitives";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/utils";
import { ChangePasswordForm } from "./change-password";

export function AccountPage() {
  const { me } = useAuth();
  if (!me) return null;
  return (
    <div className="animate-in max-w-3xl">
      <PageHeader title="Account" description="Your profile and password." />
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader title="Profile" />
          <dl className="space-y-3 px-4 py-4 text-sm">
            <div>
              <dt className="text-[11px] text-ink-3">Name</dt>
              <dd>{me.full_name || "—"}</dd>
            </div>
            <div>
              <dt className="text-[11px] text-ink-3">Username</dt>
              <dd className="font-mono">{me.username}</dd>
            </div>
            <div>
              <dt className="text-[11px] text-ink-3">Email</dt>
              <dd>{me.email}</dd>
            </div>
            <div>
              <dt className="text-[11px] text-ink-3">Role</dt>
              <dd>
                <Badge tone="brand" className="capitalize">
                  {me.role}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className="text-[11px] text-ink-3">Data access</dt>
              <dd>
                {me.scope_restricted
                  ? me.networks.map((n) => n.name).join(", ") || "No networks"
                  : "All networks"}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] text-ink-3">Last sign-in</dt>
              <dd>{fmtDate(me.last_login_at, true)}</dd>
            </div>
          </dl>
        </Card>
        <Card>
          <CardHeader title="Change password" />
          <div className="px-4 py-4">
            <ChangePasswordForm />
          </div>
        </Card>
      </div>
    </div>
  );
}
