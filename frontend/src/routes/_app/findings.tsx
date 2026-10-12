import { createFileRoute } from "@tanstack/react-router";
import { FindingsPage } from "@/features/findings/findings-page";
import { parseFindingsSearch } from "@/lib/search";

export const Route = createFileRoute("/_app/findings")({
  validateSearch: parseFindingsSearch,
  component: function FindingsRoute() {
    return <FindingsPage search={Route.useSearch()} />;
  },
});
