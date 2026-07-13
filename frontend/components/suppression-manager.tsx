"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useAddSuppressionEntry,
  useRemoveSuppressionEntry,
  useSuppressionEntries,
} from "@/lib/hooks/use-suppression";

export function SuppressionManager() {
  const { data, isPending, isError, error } = useSuppressionEntries();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Suppression list</CardTitle>
        <CardDescription>
          Emails on this list are checked before any send. Add an address to
          block outreach to it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AddSuppressionForm />

        {isPending && <Skeleton className="h-40 w-full" />}

        {isError && (
          <p className="text-destructive text-sm">
            Failed to load suppression list: {error.message}
          </p>
        )}

        {data && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Added by</TableHead>
                <TableHead>Added</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="text-muted-foreground py-8 text-center"
                  >
                    No suppressed addresses.
                  </TableCell>
                </TableRow>
              )}
              {data.map((entry) => (
                <SuppressionRow key={entry.id} entryId={entry.id} email={entry.email} reason={entry.reason} addedBy={entry.added_by} createdAt={entry.created_at} />
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function AddSuppressionForm() {
  const [email, setEmail] = useState("");
  const [reason, setReason] = useState("");
  const add = useAddSuppressionEntry();

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    add.mutate(
      { email, reason: reason || null },
      {
        onSuccess: () => {
          toast.success(`${email} added to the suppression list.`);
          setEmail("");
          setReason("");
        },
        onError: (mutationError) => {
          toast.error(`Failed to add: ${mutationError.message}`);
        },
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
      <div className="space-y-2">
        <Label htmlFor="suppress-email">Email</Label>
        <Input
          id="suppress-email"
          type="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="buyer@example.com"
          className="w-64"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="suppress-reason">Reason (optional)</Label>
        <Input
          id="suppress-reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Opted out"
          className="w-64"
        />
      </div>
      <Button type="submit" disabled={add.isPending}>
        {add.isPending ? "Adding…" : "Add"}
      </Button>
    </form>
  );
}

function SuppressionRow({
  entryId,
  email,
  reason,
  addedBy,
  createdAt,
}: {
  entryId: string;
  email: string;
  reason: string | null;
  addedBy: string;
  createdAt: string;
}) {
  const remove = useRemoveSuppressionEntry();

  function handleRemove() {
    remove.mutate(entryId, {
      onSuccess: () => toast.success(`${email} removed from the suppression list.`),
      onError: (mutationError) => toast.error(`Failed to remove: ${mutationError.message}`),
    });
  }

  return (
    <TableRow>
      <TableCell>{email}</TableCell>
      <TableCell>{reason ?? "—"}</TableCell>
      <TableCell>{addedBy}</TableCell>
      <TableCell>{new Date(createdAt).toLocaleDateString()}</TableCell>
      <TableCell>
        <Button
          variant="outline"
          size="sm"
          disabled={remove.isPending}
          onClick={handleRemove}
        >
          Remove
        </Button>
      </TableCell>
    </TableRow>
  );
}
