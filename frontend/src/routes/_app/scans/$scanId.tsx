import { createFileRoute } from "@tanstack/react-router";
import { ScanDetailPage } from "@/features/scans/scan-detail";

export const Route = createFileRoute("/_app/scans/$scanId")({
  component: function ScanRoute() {
    return <ScanDetailPage id={Number(Route.useParams().scanId)} />;
  },
});
