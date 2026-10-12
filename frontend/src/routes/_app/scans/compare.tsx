import { createFileRoute } from "@tanstack/react-router";
import { ComparePage, type CompareSearch } from "@/features/scans/compare-page";

const num = (v: unknown) => (Number(v) > 0 ? Number(v) : undefined);
const KINDS = ["new", "fixed", "persisting"] as const;

export const Route = createFileRoute("/_app/scans/compare")({
  validateSearch: (s: Record<string, unknown>): CompareSearch => ({
    base: num(s.base),
    compare: num(s.compare),
    kind: KINDS.find((k) => k === s.kind),
    page: num(s.page),
    finding: num(s.finding),
  }),
  component: function CompareRoute() {
    return <ComparePage search={Route.useSearch()} />;
  },
});
