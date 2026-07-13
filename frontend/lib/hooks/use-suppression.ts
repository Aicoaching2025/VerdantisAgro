"use client";

import { useAuth } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addSuppressionEntry,
  listSuppressionEntries,
  removeSuppressionEntry,
} from "@/lib/api/suppression";

export function useSuppressionEntries() {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["suppression"],
    queryFn: async () => listSuppressionEntries(await getToken()),
  });
}

export function useAddSuppressionEntry() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      email,
      reason,
    }: {
      email: string;
      reason: string | null;
    }) => addSuppressionEntry(await getToken(), email, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppression"] });
    },
  });
}

export function useRemoveSuppressionEntry() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (entryId: string) =>
      removeSuppressionEntry(await getToken(), entryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppression"] });
    },
  });
}
