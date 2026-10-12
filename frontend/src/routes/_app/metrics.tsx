import { createFileRoute } from "@tanstack/react-router";
import { MetricsPage } from "@/features/workflow/metrics-page";

export const Route = createFileRoute("/_app/metrics")({ component: MetricsPage });
