import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext, useEffect } from "react";
import { ApiError, api, onUnauthorized } from "./api";
import type { Me } from "./types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  can: (perm: string) => boolean;
  refetch: () => Promise<unknown>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.get<Me>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          // Access token may simply be expired: try the refresh cookie once
          try {
            return await api.post<Me>("/auth/refresh");
          } catch {
            return null;
          }
        }
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    onUnauthorized.handler = () => qc.setQueryData(["me"], null);
  }, [qc]);

  const me = query.data ?? null;
  const value: AuthState = {
    me,
    loading: query.isLoading,
    can: (perm) => !!me?.permissions.includes(perm),
    refetch: query.refetch,
    logout: async () => {
      await api.post("/auth/logout").catch(() => {});
      qc.clear();
      qc.setQueryData(["me"], null);
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
