import { createFileRoute } from "@tanstack/react-router";
import { ApprovalsPage } from "@/features/workflow/approvals-page";

export const Route = createFileRoute("/_app/approvals")({
  validateSearch: (s: Record<string, unknown>): { finding?: number } => ({
    finding: Number(s.finding) || undefined,
  }),
  component: function ApprovalsRoute() {
    return <ApprovalsPage finding={Route.useSearch().finding} />;
  },
});
