"use client";

import { useState } from "react";
import Link from "next/link";

import { LeadStatusBadge } from "@/components/lead-status-badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useLeads } from "@/lib/hooks/use-leads";
import type { LeadSource, LeadStatus } from "@/lib/api/types";

const STATUS_OPTIONS: LeadStatus[] = [
  "NEW",
  "VERIFYING",
  "QUALIFIED",
  "DISQUALIFIED",
  "PENDING_APPROVAL",
  "APPROVED",
  "REJECTED",
  "ROUTED",
  "DISCARDED",
];

const PAGE_SIZE = 25;

interface LeadsTableProps {
  /** Fixed source filter -- the Intake page pins this to INBOUND_FORM. */
  source?: LeadSource;
  showSourceColumn?: boolean;
}

export function LeadsTable({ source, showSourceColumn = true }: LeadsTableProps) {
  const [status, setStatus] = useState<LeadStatus | "ALL">("ALL");
  const [offset, setOffset] = useState(0);

  const { data, isPending, isError, error } = useLeads({
    source,
    status: status === "ALL" ? undefined : status,
    limit: PAGE_SIZE,
    offset,
  });

  const columnCount = showSourceColumn ? 7 : 6;

  return (
    <div className="space-y-4">
      <Select
        value={status}
        onValueChange={(value) => {
          setStatus(value as LeadStatus | "ALL");
          setOffset(0);
        }}
      >
        <SelectTrigger className="w-56">
          <SelectValue placeholder="All statuses" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="ALL">All statuses</SelectItem>
          {STATUS_OPTIONS.map((option) => (
            <SelectItem key={option} value={option}>
              {option.replaceAll("_", " ")}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {isPending && <Skeleton className="h-64 w-full" />}

      {isError && (
        <p className="text-destructive text-sm">
          Failed to load leads: {error.message}
        </p>
      )}

      {data && (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Company</TableHead>
                {showSourceColumn && <TableHead>Source</TableHead>}
                <TableHead>Status</TableHead>
                <TableHead>Commodity</TableHead>
                <TableHead>Fit score</TableHead>
                <TableHead>Routed to</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={columnCount}
                    className="text-muted-foreground py-8 text-center"
                  >
                    No leads found.
                  </TableCell>
                </TableRow>
              )}
              {data.items.map((lead) => (
                <TableRow key={lead.id}>
                  <TableCell>
                    <Link
                      href={`/dossier/${lead.id}`}
                      className="font-medium hover:underline"
                    >
                      {lead.company_legal_name ?? "Unknown company"}
                    </Link>
                  </TableCell>
                  {showSourceColumn && (
                    <TableCell>
                      {lead.source === "OUTBOUND_DISCOVERY" ? "Outbound" : "Inbound"}
                    </TableCell>
                  )}
                  <TableCell>
                    <LeadStatusBadge status={lead.status} />
                  </TableCell>
                  <TableCell>{lead.requested_commodity ?? "—"}</TableCell>
                  <TableCell>
                    {lead.fit_score != null ? lead.fit_score.toFixed(2) : "—"}
                  </TableCell>
                  <TableCell>{lead.routed_to ?? "—"}</TableCell>
                  <TableCell>
                    {new Date(lead.created_at).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="flex items-center justify-between">
            <p className="text-muted-foreground text-sm">{data.total} total</p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={offset + PAGE_SIZE >= data.total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
