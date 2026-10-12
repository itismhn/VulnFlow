import { createFileRoute } from "@tanstack/react-router";
import { RequirePerm } from "@/components/states";
import { UsersPage } from "@/features/admin/users-page";

export const Route = createFileRoute("/_app/admin/users")({
  component: () => (
    <RequirePerm perm="users:manage">
      <UsersPage />
    </RequirePerm>
  ),
});
