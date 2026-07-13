import { LeadsTable } from "@/components/leads-table";

export default function InboxPage() {
  return (
    <main className="flex-1 p-8">
      <h1 className="text-2xl font-semibold">Lead Inbox</h1>
      <p className="text-muted-foreground mt-2">
        Unified queue of discovered and inbound leads, filterable by status.
      </p>
      <div className="mt-6">
        <LeadsTable />
      </div>
    </main>
  );
}
