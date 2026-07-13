import { apiRequest } from "@/lib/api/client";
import { suppressionEntrySchema, type SuppressionEntry } from "@/lib/api/types";
import { TENANT_SLUG } from "@/lib/config";
import { z } from "zod";

export async function listSuppressionEntries(
  token: string | null,
): Promise<SuppressionEntry[]> {
  const data = await apiRequest(`/tenants/${TENANT_SLUG}/suppression`, token);
  return z.array(suppressionEntrySchema).parse(data);
}

export async function addSuppressionEntry(
  token: string | null,
  email: string,
  reason: string | null,
): Promise<SuppressionEntry> {
  const data = await apiRequest(`/tenants/${TENANT_SLUG}/suppression`, token, {
    method: "POST",
    body: JSON.stringify({ email, reason }),
  });
  return suppressionEntrySchema.parse(data);
}

export async function removeSuppressionEntry(
  token: string | null,
  entryId: string,
): Promise<void> {
  await apiRequest(`/tenants/${TENANT_SLUG}/suppression/${entryId}`, token, {
    method: "DELETE",
  });
}
