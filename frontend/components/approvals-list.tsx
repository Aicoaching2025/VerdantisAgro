"use client";

import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useApprovals, useDecideApproval } from "@/lib/hooks/use-outbound";
import type { ApprovalItem } from "@/lib/api/types";

export function ApprovalsList() {
  const { data, isPending, isError, error } = useApprovals();

  if (isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <p className="text-destructive text-sm">
        Failed to load approvals: {error.message}
      </p>
    );
  }

  if (data.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No drafts are waiting on a decision right now.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {data.map((item) => (
        <ApprovalCard key={item.lead_id} item={item} />
      ))}
    </div>
  );
}

function ApprovalCard({ item }: { item: ApprovalItem }) {
  const decide = useDecideApproval();

  function handleDecision(action: "approve" | "reject") {
    decide.mutate(
      { leadId: item.lead_id, action },
      {
        onSuccess: () => {
          toast.success(
            action === "approve"
              ? `Approved — ${item.legal_name} will sync to CRM.`
              : `Rejected ${item.legal_name}.`,
          );
        },
        onError: (mutationError) => {
          toast.error(`Failed to record decision: ${mutationError.message}`);
        },
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-3">
          <span>
            {item.legal_name}
            {item.country && (
              <span className="text-muted-foreground font-normal"> · {item.country}</span>
            )}
          </span>
          {item.fit_score != null && (
            <Badge variant="secondary">Fit {item.fit_score.toFixed(2)}</Badge>
          )}
        </CardTitle>
        {item.decision_maker_email && (
          <CardDescription>To: {item.decision_maker_email}</CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {item.fit_reasons.length > 0 && (
          <div>
            <p className="text-sm font-medium">Why this fit score</p>
            <ul className="text-muted-foreground mt-1 list-inside list-disc text-sm">
              {item.fit_reasons.map((reason, index) => (
                <li key={index}>{reason}</li>
              ))}
            </ul>
          </div>
        )}

        {Object.keys(item.credibility).length > 0 && (
          <div>
            <p className="text-sm font-medium">Credibility</p>
            <div className="mt-1 flex flex-wrap gap-2">
              {Object.entries(item.credibility).map(([checkType, verdict]) => (
                <Badge
                  key={checkType}
                  variant={
                    verdict === "PASS"
                      ? "success"
                      : verdict === "FAIL"
                        ? "destructive"
                        : "warning"
                  }
                >
                  {checkType.replaceAll("_", " ")}: {verdict}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {item.draft_body && (
          <div>
            <p className="text-sm font-medium">Draft message</p>
            <p className="bg-muted mt-1 rounded-md p-3 text-sm whitespace-pre-wrap">
              {item.draft_body}
            </p>
          </div>
        )}
      </CardContent>
      <CardFooter className="gap-2">
        <Button
          disabled={decide.isPending}
          onClick={() => handleDecision("approve")}
        >
          Approve
        </Button>
        <Button
          variant="outline"
          disabled={decide.isPending}
          onClick={() => handleDecision("reject")}
        >
          Reject
        </Button>
      </CardFooter>
    </Card>
  );
}
