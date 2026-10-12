import { createFileRoute } from "@tanstack/react-router";
import { ScansPage } from "@/features/scans/scans-page";

export const Route = createFileRoute("/_app/scans/")({ component: ScansPage });
