import { LeadsTable } from "@/components/leads-table";

export default function IntakePage() {
  return (
    <main className="flex-1 p-8">
      <h1 className="text-2xl font-semibold">Inbound Intake</h1>
      <p className="text-muted-foreground mt-2">
        Submissions from the embeddable form, with normalized commodity-trade
        fields (Incoterms, payment terms) and routing status. Open a lead for
        the full intake payload and dossier evidence.
      </p>
      <div className="mt-6">
        <LeadsTable source="INBOUND_FORM" showSourceColumn={false} />
      </div>
    </main>
  );
}
