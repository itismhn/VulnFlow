import { createFileRoute } from "@tanstack/react-router";
import { VulnerabilitiesPage } from "@/features/vulnerabilities/vulnerabilities-page";

export const Route = createFileRoute("/_app/vulnerabilities/")({ component: VulnerabilitiesPage });
