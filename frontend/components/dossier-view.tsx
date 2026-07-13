"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LeadStatusBadge } from "@/components/lead-status-badge";
import { VerdictBadge } from "@/components/verdict-badge";
import { useLead } from "@/lib/hooks/use-leads";

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString();
}

export function DossierView({ leadId }: { leadId: string }) {
  const { data, isPending, isError, error } = useLead(leadId);

  if (isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <p className="text-destructive text-sm">
        Failed to load lead: {error.message}
      </p>
    );
  }

  const { lead, incoterm, payment_terms, intake, dossier } = data;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3 text-xl">
            {lead.company_legal_name ?? "Unknown company"}
            <LeadStatusBadge status={lead.status} />
          </CardTitle>
          <CardDescription>
            {lead.source === "OUTBOUND_DISCOVERY" ? "Outbound discovery" : "Inbound form"}
            {" · "}
            Submitted {formatDateTime(lead.created_at)}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <Field label="Requested commodity" value={lead.requested_commodity} />
          <Field
            label="Fit score"
            value={lead.fit_score != null ? lead.fit_score.toFixed(2) : null}
          />
          <Field
            label="Credibility score"
            value={
              dossier?.credibility_score != null
                ? dossier.credibility_score.toFixed(2)
                : null
            }
          />
          <Field label="Routed to" value={lead.routed_to} />
          <Field label="Incoterm" value={incoterm} />
          <Field label="Payment terms" value={payment_terms} />
        </CardContent>
      </Card>

      {intake && (
        <Card>
          <CardHeader>
            <CardTitle>Intake details</CardTitle>
            <CardDescription>
              Raw submission fields, decrypted for authorized viewing.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
              {Object.entries(intake).map(([key, value]) => (
                <div key={key}>
                  <dt className="text-muted-foreground">
                    {key.replaceAll("_", " ")}
                  </dt>
                  <dd className="font-medium break-words">
                    {value == null || value === "" ? "—" : String(value)}
                  </dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
      )}

      {dossier ? (
        <>
          {dossier.is_sanctioned && (
            <div className="rounded-md border border-destructive bg-destructive/10 p-4 text-sm font-medium text-destructive">
              Sanctions hit on file for this company. Blocked from routing/outreach.
              {dossier.sanctions_review_suggested &&
                " A later PASS conflicts with this flag and is pending human review."}
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Verification results</CardTitle>
              <CardDescription>
                Every verdict is provenance-stamped: source, retrieval time, and
                confidence.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {dossier.verification_results.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  No verification results on file.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Check</TableHead>
                      <TableHead>Verdict</TableHead>
                      <TableHead>Source</TableHead>
                      <TableHead>Retrieved</TableHead>
                      <TableHead>Confidence</TableHead>
                      <TableHead>Evidence</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {dossier.verification_results.map((result, index) => (
                      <TableRow key={`${result.check_type}-${index}`}>
                        <TableCell>{result.check_type.replaceAll("_", " ")}</TableCell>
                        <TableCell>
                          <VerdictBadge verdict={result.verdict} />
                        </TableCell>
                        <TableCell>{result.source}</TableCell>
                        <TableCell>{formatDateTime(result.retrieved_at)}</TableCell>
                        <TableCell>{result.confidence.toFixed(2)}</TableCell>
                        <TableCell className="max-w-64 whitespace-pre-wrap">
                          {result.evidence ? JSON.stringify(result.evidence) : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Trade signals</CardTitle>
              <CardDescription>
                Derived intelligence only — never raw licensed shipment records.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {dossier.trade_signals.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  No trade signals on file.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Signal</TableHead>
                      <TableHead>Commodity</TableHead>
                      <TableHead>Band</TableHead>
                      <TableHead>Value</TableHead>
                      <TableHead>Source</TableHead>
                      <TableHead>Retrieved</TableHead>
                      <TableHead>Confidence</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {dossier.trade_signals.map((signal, index) => (
                      <TableRow key={`${signal.signal_type}-${index}`}>
                        <TableCell>{signal.signal_type.replaceAll("_", " ")}</TableCell>
                        <TableCell>{signal.commodity ?? "—"}</TableCell>
                        <TableCell>{signal.band ?? "—"}</TableCell>
                        <TableCell>{signal.numeric_value ?? "—"}</TableCell>
                        <TableCell>{signal.source}</TableCell>
                        <TableCell>{formatDateTime(signal.retrieved_at)}</TableCell>
                        <TableCell>{signal.confidence.toFixed(2)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      ) : (
        <p className="text-muted-foreground text-sm">
          No company dossier on file for this lead yet.
        </p>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="text-muted-foreground">{label}</p>
      <p className="font-medium">{value ?? "—"}</p>
    </div>
  );
}
