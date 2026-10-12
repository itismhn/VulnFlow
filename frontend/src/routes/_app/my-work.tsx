import { createFileRoute } from "@tanstack/react-router";
import { RequirePerm } from "@/components/states";
import { MyWorkPage } from "@/features/workflow/my-work-page";

export const Route = createFileRoute("/_app/my-work")({
  validateSearch: (s: Record<string, unknown>): { finding?: number } => ({
    finding: Number(s.finding) || undefined,
  }),
  component: function MyWorkRoute() {
    return (
      <RequirePerm perm="findings:update">
        <MyWorkPage finding={Route.useSearch().finding} />
      </RequirePerm>
    );
  },
});
