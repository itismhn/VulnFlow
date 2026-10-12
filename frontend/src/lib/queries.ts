import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { NetworkStats, UserBrief } from "./types";

export const useNetworks = () =>
  useQuery({
    queryKey: ["networks"],
    queryFn: () => api.get<NetworkStats[]>("/networks"),
    staleTime: 60_000,
  });

export const useZones = () =>
  useQuery({
    queryKey: ["networks", "zones"],
    queryFn: () => api.get<string[]>("/networks/zones"),
    staleTime: 60_000,
  });

export const useDirectory = (enabled = true) =>
  useQuery({
    queryKey: ["users", "directory"],
    queryFn: () => api.get<UserBrief[]>("/users/directory"),
    staleTime: 300_000,
    enabled,
  });
