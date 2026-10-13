import { createFileRoute } from "@tanstack/react-router";
import { SoftwarePage } from "@/features/software/software-page";
import { parseSoftwareSearch } from "@/lib/search";

export const Route = createFileRoute("/_app/software")({
  validateSearch: parseSoftwareSearch,
  component: function SoftwareRoute() {
    return <SoftwarePage search={Route.useSearch()} />;
  },
});
