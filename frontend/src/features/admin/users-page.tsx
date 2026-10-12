import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Lock, MoreHorizontal, Pencil, Plus, Trash2, UserX } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Dialog, DropdownMenu, MenuItem, MenuSeparator } from "@/components/ui/overlay";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useNetworks } from "@/lib/queries";
import type { Role, User } from "@/lib/types";
import { fmtDate, fmtRelative } from "@/lib/utils";

const ROLE_INFO: Record<Role, string> = {
  admin: "Everything, including users, settings, approving risk acceptance and deleting scans",
  analyst: "Import scans, triage findings, request risk acceptance, manage networks and templates",
  viewer: "Read-only access and report generation",
};

function generatePassword(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%&*-_";
  const bytes = crypto.getRandomValues(new Uint32Array(18));
  let pw = Array.from(bytes, (b) => chars[b % chars.length]).join("");
  pw += "aA1!"; // guarantee every character class
  return pw;
}

export function UsersPage() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const { data: users = [] } = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/users") });
  const [editing, setEditing] = useState<Partial<User> | null>(null);
  const [resetting, setResetting] = useState<User | null>(null);
  const [deleting, setDeleting] = useState<User | null>(null);

  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      api.patch(`/users/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success("User updated");
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/users/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setDeleting(null);
      toast.success("User deleted");
    },
  });

  return (
    <div className="animate-in">
      <PageHeader
        title="Users"
        description="Local accounts and their access. New users must change their password at first sign-in."
        actions={
          <Button
            variant="primary"
            onClick={() => setEditing({ role: "analyst", scope_restricted: false, networks: [] })}
          >
            <Plus className="size-4" /> Add user
          </Button>
        }
      />
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface-2/60 text-left text-xs text-ink-3">
              <tr>
                <th className="px-4 py-2 font-medium">User</th>
                <th className="px-4 py-2 font-medium">Role</th>
                <th className="px-4 py-2 font-medium">Data access</th>
                <th className="px-4 py-2 font-medium">Last sign-in</th>
                <th className="px-4 py-2 font-medium">State</th>
                <th className="w-10 px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {users.map((u) => {
                const locked = u.locked_until && new Date(u.locked_until) > new Date();
                return (
                  <tr key={u.id} className={u.is_active ? "" : "opacity-60"}>
                    <td className="px-4 py-2.5">
                      <div className="font-medium">
                        {u.full_name || u.username}
                        {u.id === me?.id && <span className="ml-1.5 text-xs text-ink-3">(you)</span>}
                      </div>
                      <div className="text-xs text-ink-3">
                        {u.username} · {u.email}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge tone={u.role === "admin" ? "brand" : "neutral"} className="capitalize">
                        {u.role}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-ink-2">
                      {u.scope_restricted
                        ? u.networks.length
                          ? u.networks.map((n) => n.name).join(", ")
                          : "No networks"
                        : "All networks"}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-ink-2" title={fmtDate(u.last_login_at, true)}>
                      {u.last_login_at ? fmtRelative(u.last_login_at) : "Never"}
                    </td>
                    <td className="space-x-1 px-4 py-2.5">
                      {!u.is_active && <Badge>Disabled</Badge>}
                      {locked && (
                        <Badge tone="danger">
                          <Lock className="size-3" /> Locked
                        </Badge>
                      )}
                      {u.must_change_password && <Badge tone="warn">Must change password</Badge>}
                      {u.is_active && !locked && !u.must_change_password && <Badge tone="ok">Active</Badge>}
                    </td>
                    <td className="px-4 py-2.5">
                      <DropdownMenu
                        trigger={
                          <Button size="icon" variant="ghost" aria-label={`Actions for ${u.username}`}>
                            <MoreHorizontal className="size-4" />
                          </Button>
                        }
                      >
                        <MenuItem onSelect={() => setEditing(u)}>
                          <Pencil className="size-4" /> Edit
                        </MenuItem>
                        <MenuItem onSelect={() => setResetting(u)}>
                          <KeyRound className="size-4" /> Reset password
                        </MenuItem>
                        {u.id !== me?.id && (
                          <>
                            <MenuItem
                              onSelect={() => update.mutate({ id: u.id, body: { is_active: !u.is_active } })}
                            >
                              <UserX className="size-4" />{" "}
                              {u.is_active ? "Disable account" : "Enable account"}
                            </MenuItem>
                            <MenuSeparator />
                            <MenuItem danger onSelect={() => setDeleting(u)}>
                              <Trash2 className="size-4" /> Delete
                            </MenuItem>
                          </>
                        )}
                      </DropdownMenu>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {editing && <UserDialog initial={editing} onClose={() => setEditing(null)} />}
      {resetting && <ResetDialog user={resetting} onClose={() => setResetting(null)} />}
      <Dialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete ${deleting?.username}?`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => deleting && remove.mutate(deleting.id)}
            >
              Delete user
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink-2">
          Their audit trail is kept. Findings assigned to them become unassigned. Disabling the account
          instead keeps their history linked.
        </p>
      </Dialog>
    </div>
  );
}

function UserDialog({ initial, onClose }: { initial: Partial<User>; onClose: () => void }) {
  const qc = useQueryClient();
  const { data: networks = [] } = useNetworks();
  const isNew = !initial.id;
  const [form, setForm] = useState({
    username: initial.username ?? "",
    email: initial.email ?? "",
    full_name: initial.full_name ?? "",
    role: (initial.role ?? "analyst") as Role,
    scope_restricted: initial.scope_restricted ?? false,
    network_ids: initial.networks?.map((n) => n.id) ?? [],
    password: isNew ? generatePassword() : "",
  });
  const save = useMutation({
    mutationFn: () => {
      const { username, password, ...rest } = form;
      return isNew
        ? api.post<User>("/users", { ...rest, username, password })
        : api.patch<User>(`/users/${initial.id}`, rest);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success(isNew ? "User created. Share the temporary password securely." : "User updated");
      onClose();
    },
  });

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={isNew ? "Add user" : `Edit ${initial.username}`}
      className="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
            {isNew ? "Create user" : "Save changes"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Username">
            <Input
              value={form.username}
              disabled={!isNew}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
          </Field>
          <Field label="Full name">
            <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </Field>
          <Field label="Email" className="sm:col-span-2">
            <Input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Field>
        </div>
        <Field label="Role" hint={ROLE_INFO[form.role]}>
          <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
            <option value="admin">Admin</option>
            <option value="analyst">Analyst</option>
            <option value="viewer">Viewer</option>
          </Select>
        </Field>
        <div className="rounded-md border border-line p-3">
          <label className="flex items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              className="accent-[var(--brand)]"
              checked={form.scope_restricted}
              onChange={(e) => setForm({ ...form, scope_restricted: e.target.checked })}
            />
            Restrict to specific networks
          </label>
          <p className="mt-1 ml-6 text-xs text-ink-3">
            The user only sees assets, findings, scans and reports inside the selected ranges (including
            nested ranges).
          </p>
          {form.scope_restricted && (
            <div className="mt-3 ml-6 grid max-h-48 gap-1.5 overflow-y-auto sm:grid-cols-2">
              {networks.map((n) => (
                <label key={n.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="accent-[var(--brand)]"
                    checked={form.network_ids.includes(n.id)}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        network_ids: e.target.checked
                          ? [...form.network_ids, n.id]
                          : form.network_ids.filter((x) => x !== n.id),
                      })
                    }
                  />
                  {n.name} <span className="font-mono text-xs text-ink-3">{n.cidr}</span>
                </label>
              ))}
              {!networks.length && <p className="text-xs text-ink-3">Define networks first.</p>}
            </div>
          )}
        </div>
        {isNew && (
          <Field
            label="Temporary password"
            hint="The user must change it at first sign-in. Share it over a secure channel."
          >
            <div className="flex gap-2">
              <Input
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="font-mono"
              />
              <Button
                onClick={() => {
                  navigator.clipboard.writeText(form.password);
                  toast.success("Copied");
                }}
              >
                Copy
              </Button>
            </div>
          </Field>
        )}
      </div>
    </Dialog>
  );
}

function ResetDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const qc = useQueryClient();
  const [password] = useState(generatePassword);
  const reset = useMutation({
    mutationFn: () => api.post(`/users/${user.id}/reset-password`, { password }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success("Password reset and all sessions signed out");
      onClose();
    },
  });
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Reset password for ${user.username}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={reset.isPending} onClick={() => reset.mutate()}>
            Reset password
          </Button>
        </>
      }
    >
      <p className="mb-3 text-sm text-ink-2">
        Their sessions end immediately and the account is unlocked. They must set a new password at next
        sign-in.
      </p>
      <div className="flex gap-2">
        <Input readOnly value={password} className="font-mono" />
        <Button
          onClick={() => {
            navigator.clipboard.writeText(password);
            toast.success("Copied");
          }}
        >
          Copy
        </Button>
      </div>
    </Dialog>
  );
}
