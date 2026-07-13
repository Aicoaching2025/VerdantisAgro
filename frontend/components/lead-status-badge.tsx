import { Badge, type badgeVariants } from "@/components/ui/badge";
import type { LeadStatus } from "@/lib/api/types";
import type { VariantProps } from "class-variance-authority";

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>;

const STATUS_VARIANT: Record<LeadStatus, BadgeVariant> = {
  NEW: "outline",
  VERIFYING: "outline",
  QUALIFIED: "secondary",
  DISQUALIFIED: "destructive",
  PENDING_APPROVAL: "warning",
  APPROVED: "success",
  REJECTED: "destructive",
  ROUTED: "success",
  DISCARDED: "destructive",
};

export function LeadStatusBadge({ status }: { status: LeadStatus }) {
  return (
    <Badge variant={STATUS_VARIANT[status]}>
      {status.replaceAll("_", " ").toLowerCase()}
    </Badge>
  );
}
