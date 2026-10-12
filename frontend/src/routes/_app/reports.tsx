import { createFileRoute } from "@tanstack/react-router";
import { ReportsPage } from "@/features/reports/reports-page";

export const Route = createFileRoute("/_app/reports")({
  validateSearch: (s: Record<string, unknown>): { filters?: string } => ({
    filters: typeof s.filters === "string" ? s.filters : undefined,
  }),
  component: function ReportsRoute() {
    return <ReportsPage initialFilters={Route.useSearch().filters} />;
  },
});
