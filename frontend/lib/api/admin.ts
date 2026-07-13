import { apiRequest } from "@/lib/api/client";
import { tenantConfigSchema, type TenantConfig } from "@/lib/api/types";
import { TENANT_SLUG } from "@/lib/config";

export async function getTenantConfig(token: string | null): Promise<TenantConfig> {
  const data = await apiRequest(`/tenants/${TENANT_SLUG}/config`, token);
  return tenantConfigSchema.parse(data);
}

export async function updateTenantConfig(
  token: string | null,
  config: TenantConfig,
): Promise<TenantConfig> {
  const data = await apiRequest(`/tenants/${TENANT_SLUG}/config`, token, {
    method: "PUT",
    body: JSON.stringify(config),
  });
  return tenantConfigSchema.parse(data);
}
