import { Badge } from "@/components/ui/badge";
import type { Verdict } from "@/lib/api/types";

const VERDICT_VARIANT = {
  PASS: "success",
  FAIL: "destructive",
  INCONCLUSIVE: "warning",
} as const;

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <Badge variant={VERDICT_VARIANT[verdict]}>{verdict}</Badge>;
}
