export default async function DossierPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <main className="flex-1 p-8">
      <h1 className="text-2xl font-semibold">Dossier</h1>
      <p className="text-muted-foreground mt-2">
        Company {id}: derived trade signals, provenance/evidence trail, and
        verification verdict with reasons.
      </p>
    </main>
  );
}
