import { z } from "zod";
import { apiFetch } from "@/lib/api/client";

const healthResponseSchema = z.object({
  status: z.string(),
});

export type HealthResponse = z.infer<typeof healthResponseSchema>;

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await apiFetch("/healthz");
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return healthResponseSchema.parse(await response.json());
}
