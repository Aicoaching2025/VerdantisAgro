"use client";

import { useAuth } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";

import { getLead, listLeads, type ListLeadsParams } from "@/lib/api/leads";

export function useLeads(params: ListLeadsParams) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["leads", params],
    queryFn: async () => listLeads(await getToken(), params),
  });
}

export function useLead(leadId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["lead", leadId],
    queryFn: async () => getLead(await getToken(), leadId),
    enabled: Boolean(leadId),
  });
}
