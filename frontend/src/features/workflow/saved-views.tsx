import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, Trash2, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Dialog, DropdownMenu, MenuItem, MenuLabel, MenuSeparator } from "@/components/ui/overlay";
import { Button, Field, Input } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { FindingsSearch } from "@/lib/search";
import type { SavedView } from "@/lib/types";

/** Save the current findings filters/grouping/sort as a named view, personal or shared. */
export function SavedViewsMenu({
  search,
  onApply,
}: {
  search: FindingsSearch;
  onApply: (query: FindingsSearch) => void;
}) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const { data: views = [] } = useQuery({
    queryKey: ["views"],
    queryFn: () => api.get<SavedView[]>("/views"),
  });
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [shared, setShared] = useState(false);

  const { page: _p, finding: _f, ...query } = search;
  const create = useMutation({
    mutationFn: () => api.post<SavedView>("/views", { name, shared, query }),
    onSuccess: (v) => {
      toast.success(`Saved view "${v.name}"`);
      qc.invalidateQueries({ queryKey: ["views"] });
      setSaving(false);
      setName("");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/views/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["views"] }),
    onError: (e: Error) => toast.error(e.message),
  });

  const mine = views.filter((v) => v.owner.id === me?.id);
  const team = views.filter((v) => v.owner.id !== me?.id);

  return (
    <>
      <DropdownMenu
        trigger={
          <Button>
            <Bookmark className="size-4" /> Views
          </Button>
        }
      >
        {views.length === 0 && <MenuLabel>No saved views yet</MenuLabel>}
        {mine.length > 0 && <MenuLabel>My views</MenuLabel>}
        {mine.map((v) => (
          <MenuItem key={v.id} onSelect={() => onApply(v.query as FindingsSearch)}>
            <span className="flex-1 truncate">{v.name}</span>
            {v.shared && <Users className="size-3.5 text-ink-3" aria-label="Shared" />}
            <button
              type="button"
              aria-label={`Delete view ${v.name}`}
              className="rounded p-0.5 text-ink-3 hover:text-critical"
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
                remove.mutate(v.id);
              }}
            >
              <Trash2 className="size-3.5" />
            </button>
          </MenuItem>
        ))}
        {team.length > 0 && <MenuLabel>Shared by the team</MenuLabel>}
        {team.map((v) => (
          <MenuItem key={v.id} onSelect={() => onApply(v.query as FindingsSearch)}>
            <span className="flex-1 truncate">{v.name}</span>
            <span className="text-[11px] text-ink-3">{v.owner.username}</span>
          </MenuItem>
        ))}
        <MenuSeparator />
        <MenuItem onSelect={() => setSaving(true)}>Save current view…</MenuItem>
      </DropdownMenu>
      <Dialog
        open={saving}
        onOpenChange={setSaving}
        title="Save view"
        description="Saves the current filters, grouping, and sort order."
        footer={
          <>
            <Button variant="ghost" onClick={() => setSaving(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={!name.trim()}
              loading={create.isPending}
              onClick={() => create.mutate()}
            >
              Save view
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Name">
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Exploitable criticals in Cards/PCI"
              onKeyDown={(e) => e.key === "Enter" && name.trim() && create.mutate()}
            />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
            Share with everyone on the team
          </label>
        </div>
      </Dialog>
    </>
  );
}
