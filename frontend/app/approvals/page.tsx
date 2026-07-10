export default function ApprovalsPage() {
  return (
    <main className="flex-1 p-8">
      <h1 className="text-2xl font-semibold">Approval / Outreach</h1>
      <p className="text-muted-foreground mt-2">
        Draft messages awaiting human approval — approve, edit, or reject.
        Every outbound send passes through here; nothing sends automatically.
      </p>
    </main>
  );
}
