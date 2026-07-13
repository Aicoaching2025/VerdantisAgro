import { SuppressionManager } from "@/components/suppression-manager";
import { TenantConfigForm } from "@/components/tenant-config-form";

export default function AdminPage() {
  return (
    <main className="flex-1 space-y-8 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Admin / Settings</h1>
        <p className="text-muted-foreground mt-2">
          Tenant config (commodity set, regions, ICP thresholds, routing
          rules) and the outreach suppression list.
        </p>
      </div>

      <TenantConfigForm />
      <SuppressionManager />
    </main>
  );
}
