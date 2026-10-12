import { createFileRoute } from "@tanstack/react-router";
import { RequirePerm } from "@/components/states";
import { AuditPage } from "@/features/admin/audit-page";

export const Route = createFileRoute("/_app/admin/audit")({
  component: () => (
    <RequirePerm perm="audit:read">
      <AuditPage />
    </RequirePerm>
  ),
});
