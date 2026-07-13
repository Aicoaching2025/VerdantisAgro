"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantConfig, useUpdateTenantConfig } from "@/lib/hooks/use-admin";
import type { RoutingTarget, TenantConfig } from "@/lib/api/types";

const ROUTING_TARGETS: RoutingTarget[] = ["SALES", "ORGANICA", "SUPPORT", "TRIAGE"];

function toCsv(values: string[] | null): string {
  return (values ?? []).join(", ");
}

function fromCsv(value: string): string[] {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function TenantConfigForm() {
  const { data, isPending, isError, error } = useTenantConfig();

  if (isPending) return <Skeleton className="h-96 w-full" />;
  if (isError) {
    return (
      <p className="text-destructive text-sm">
        Failed to load tenant config: {error.message}
      </p>
    );
  }

  return <TenantConfigFormInner initial={data} />;
}

function TenantConfigFormInner({ initial }: { initial: TenantConfig }) {
  const [form, setForm] = useState(initial);
  const update = useUpdateTenantConfig();

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    update.mutate(form, {
      onSuccess: () => toast.success("Tenant config saved."),
      onError: (mutationError) => toast.error(`Save failed: ${mutationError.message}`),
    });
  }

  return (
    <Card>
      <form onSubmit={handleSubmit}>
        <CardHeader>
          <CardTitle>Tenant configuration</CardTitle>
          <CardDescription>
            Commodity set, regions, ICP thresholds, and routing rules —
            tenant-scoped, never hardcoded.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="commodities">Commodities (comma-separated)</Label>
            <Input
              id="commodities"
              value={toCsv(form.commodities)}
              onChange={(event) =>
                setForm({ ...form, commodities: fromCsv(event.target.value) })
              }
              placeholder="cocoa, cashew, sesame"
            />
          </div>

          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="regions">Regions (comma-separated)</Label>
            <Input
              id="regions"
              value={toCsv(form.regions)}
              onChange={(event) =>
                setForm({ ...form, regions: fromCsv(event.target.value) || null })
              }
              placeholder="EU, West Africa"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="outbound-threshold">Outbound fit threshold</Label>
            <Input
              id="outbound-threshold"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={form.outbound_fit_threshold}
              onChange={(event) =>
                setForm({
                  ...form,
                  outbound_fit_threshold: Number(event.target.value),
                })
              }
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="inbound-threshold">Inbound fit threshold</Label>
            <Input
              id="inbound-threshold"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={form.inbound_fit_threshold}
              onChange={(event) =>
                setForm({
                  ...form,
                  inbound_fit_threshold: Number(event.target.value),
                })
              }
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="routing-target">Default routing target</Label>
            <Select
              value={form.default_routing_target}
              onValueChange={(value) =>
                setForm({ ...form, default_routing_target: value as RoutingTarget })
              }
            >
              <SelectTrigger id="routing-target" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROUTING_TARGETS.map((target) => (
                  <SelectItem key={target} value={target}>
                    {target}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="slack-webhook">Slack webhook URL</Label>
            <Input
              id="slack-webhook"
              value={form.slack_webhook_url ?? ""}
              onChange={(event) =>
                setForm({
                  ...form,
                  slack_webhook_url: event.target.value || null,
                })
              }
              placeholder="https://hooks.slack.com/services/..."
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="ack-from-email">Ack from-email</Label>
            <Input
              id="ack-from-email"
              value={form.ack_from_email ?? ""}
              onChange={(event) =>
                setForm({ ...form, ack_from_email: event.target.value || null })
              }
              placeholder="leads@verdantisagro.com"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="ack-from-name">Ack from-name</Label>
            <Input
              id="ack-from-name"
              value={form.ack_from_name}
              onChange={(event) =>
                setForm({ ...form, ack_from_name: event.target.value })
              }
            />
          </div>
        </CardContent>
        <CardFooter>
          <Button type="submit" disabled={update.isPending}>
            {update.isPending ? "Saving…" : "Save changes"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
