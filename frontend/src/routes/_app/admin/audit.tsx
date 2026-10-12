import { createFileRoute } from "@tanstack/react-router";
import { AuditPage } from "@/features/admin/audit-page";

export const Route = createFileRoute("/_app/admin/audit")({ component: AuditPage });
