import { apiRequest } from "@/lib/api/client";
import {
  approvalItemSchema,
  outboundRunResponseSchema,
  type ApprovalDecision,
  type ApprovalItem,
  type OutboundRunResponse,
} from "@/lib/api/types";
import { TENANT_SLUG } from "@/lib/config";
import { z } from "zod";

export async function listApprovals(token: string | null): Promise<ApprovalItem[]> {
  const data = await apiRequest(`/tenants/${TENANT_SLUG}/outbound/approvals`, token);
  return z.array(approvalItemSchema).parse(data);
}

export async function decideApproval(
  token: string | null,
  leadId: string,
  action: ApprovalDecision,
): Promise<void> {
  await apiRequest(
    `/tenants/${TENANT_SLUG}/outbound/approvals/${leadId}/decision`,
    token,
    {
      method: "POST",
      body: JSON.stringify({ action }),
    },
  );
}

export async function triggerOutboundRun(
  token: string | null,
  file: File,
): Promise<OutboundRunResponse> {
  const formData = new FormData();
  formData.append("export_file", file);
  const data = await apiRequest(`/tenants/${TENANT_SLUG}/outbound/runs`, token, {
    method: "POST",
    body: formData,
  });
  return outboundRunResponseSchema.parse(data);
}
