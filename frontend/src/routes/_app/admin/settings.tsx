import { createFileRoute } from "@tanstack/react-router";
import { RequirePerm } from "@/components/states";
import { SettingsPage } from "@/features/admin/settings-page";

export const Route = createFileRoute("/_app/admin/settings")({
  component: () => (
    <RequirePerm perm="settings:manage">
      <SettingsPage />
    </RequirePerm>
  ),
});
