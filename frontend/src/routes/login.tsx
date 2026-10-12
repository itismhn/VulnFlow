import { createFileRoute, Navigate } from "@tanstack/react-router";
import { LoginPage } from "@/features/auth/login";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/login")({
  component: () => {
    const { me, loading } = useAuth();
    if (!loading && me) return <Navigate to="/" />;
    return <LoginPage />;
  },
});
