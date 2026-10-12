import { createFileRoute } from "@tanstack/react-router";
import { SettingsPage } from "@/features/admin/settings-page";

export const Route = createFileRoute("/_app/admin/settings")({ component: SettingsPage });
