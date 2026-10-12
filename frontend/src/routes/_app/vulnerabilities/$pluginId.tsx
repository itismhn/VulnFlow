import { createFileRoute } from "@tanstack/react-router";
import { VulnerabilityDetailPage } from "@/features/vulnerabilities/vulnerability-detail";

export const Route = createFileRoute("/_app/vulnerabilities/$pluginId")({
  component: function VulnRoute() {
    return <VulnerabilityDetailPage id={Number(Route.useParams().pluginId)} />;
  },
});
