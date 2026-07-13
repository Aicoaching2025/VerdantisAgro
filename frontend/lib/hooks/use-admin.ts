"use client";

import { useAuth } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getTenantConfig, updateTenantConfig } from "@/lib/api/admin";
import type { TenantConfig } from "@/lib/api/types";

export function useTenantConfig() {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["tenant-config"],
    queryFn: async () => getTenantConfig(await getToken()),
  });
}

export function useUpdateTenantConfig() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (config: TenantConfig) =>
      updateTenantConfig(await getToken(), config),
    onSuccess: (config) => {
      queryClient.setQueryData(["tenant-config"], config);
    },
  });
}
