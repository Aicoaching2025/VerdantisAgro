"use client";

import { useAuth } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  decideApproval,
  listApprovals,
  triggerOutboundRun,
} from "@/lib/api/outbound";
import type { ApprovalDecision } from "@/lib/api/types";

export function useApprovals() {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["approvals"],
    queryFn: async () => listApprovals(await getToken()),
  });
}

export function useDecideApproval() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      leadId,
      action,
    }: {
      leadId: string;
      action: ApprovalDecision;
    }) => decideApproval(await getToken(), leadId, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

export function useTriggerOutboundRun() {
  const { getToken } = useAuth();
  return useMutation({
    mutationFn: async (file: File) => triggerOutboundRun(await getToken(), file),
  });
}
