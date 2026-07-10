export default function IntakePage() {
  return (
    <main className="flex-1 p-8">
      <h1 className="text-2xl font-semibold">Inbound Intake</h1>
      <p className="text-muted-foreground mt-2">
        Submissions with normalized commodity-trade fields (Incoterms,
        payment terms, volume) and routing status.
      </p>
    </main>
  );
}
