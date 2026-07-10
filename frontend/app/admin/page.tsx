export default function AdminPage() {
  return (
    <main className="flex-1 p-8">
      <h1 className="text-2xl font-semibold">Admin / Settings</h1>
      <p className="text-muted-foreground mt-2">
        Tenant config (commodity set, regions, ICP thresholds, routing
        rules), API/adapter status, and user/RBAC.
      </p>
    </main>
  );
}
