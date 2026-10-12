import { createFileRoute } from "@tanstack/react-router";
import { NetworksPage } from "@/features/networks/networks-page";

export const Route = createFileRoute("/_app/networks")({ component: NetworksPage });
