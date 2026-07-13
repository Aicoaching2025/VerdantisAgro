import { DossierView } from "@/components/dossier-view";

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
        Derived trade signals, provenance/evidence trail, and verification
        verdicts for this lead&apos;s company.
      </p>
      <div className="mt-6">
        <DossierView leadId={id} />
      </div>
    </main>
  );
}
