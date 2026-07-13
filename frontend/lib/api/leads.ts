import { apiRequest } from "@/lib/api/client";
import {
  leadDetailResponseSchema,
  leadListResponseSchema,
  type LeadDetailResponse,
  type LeadListResponse,
  type LeadSource,
  type LeadStatus,
} from "@/lib/api/types";
import { TENANT_SLUG } from "@/lib/config";

export interface ListLeadsParams {
  status?: LeadStatus;
  source?: LeadSource;
  limit?: number;
  offset?: number;
}

export async function listLeads(
  token: string | null,
  params: ListLeadsParams = {},
): Promise<LeadListResponse> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.source) search.set("source", params.source);
  search.set("limit", String(params.limit ?? 50));
  search.set("offset", String(params.offset ?? 0));

  const data = await apiRequest(
    `/tenants/${TENANT_SLUG}/leads?${search.toString()}`,
    token,
  );
  return leadListResponseSchema.parse(data);
}

export async function getLead(
  token: string | null,
  leadId: string,
): Promise<LeadDetailResponse> {
  const data = await apiRequest(`/tenants/${TENANT_SLUG}/leads/${leadId}`, token);
  return leadDetailResponseSchema.parse(data);
}
