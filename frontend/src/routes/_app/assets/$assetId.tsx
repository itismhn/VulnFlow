import { createFileRoute } from "@tanstack/react-router";
import { AssetDetailPage } from "@/features/assets/asset-detail";

export const Route = createFileRoute("/_app/assets/$assetId")({
  component: function AssetRoute() {
    return <AssetDetailPage id={Number(Route.useParams().assetId)} />;
  },
});
