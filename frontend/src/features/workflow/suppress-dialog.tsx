import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Dialog } from "@/components/ui/overlay";
import { Button, Field, Input, Textarea } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { SuppressionRule } from "@/lib/types";

/** Mark a plugin as a false positive on every host (optionally narrowed to a range or port). */
export function SuppressDialog({
  plugin,
  open,
  onOpenChange,
}: {
  plugin: { id: number; name: string };
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const [cidr, setCidr] = useState("");
  const [port, setPort] = useState("");
  const [reason, setReason] = useState("");
  const create = useMutation({
    mutationFn: () =>
      api.post<SuppressionRule>("/suppressions", {
        plugin_id: plugin.id,
        cidr: cidr.trim() || null,
        port: port ? Number(port) : null,
        reason,
      }),
    onSuccess: (rule) => {
      toast.success(`Marked ${rule.matched} findings as false positive`);
      qc.invalidateQueries({ queryKey: ["findings"] });
      qc.invalidateQueries({ queryKey: ["finding"] });
      qc.invalidateQueries({ queryKey: ["suppressions"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="False positive on all hosts"
      description={
        <>
          Creates a rule for <strong>{plugin.name}</strong>. Matching findings, including ones found by future
          imports, are marked as false positives. Deleting the rule reopens them.
        </>
      }
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!reason.trim()}
            loading={create.isPending}
            onClick={() => create.mutate()}
          >
            Create rule
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Limit to range (optional)" hint="CIDR, e.g. 10.20.0.0/16">
            <Input value={cidr} onChange={(e) => setCidr(e.target.value)} placeholder="All hosts" />
          </Field>
          <Field label="Limit to port (optional)">
            <Input
              type="number"
              min={0}
              max={65535}
              value={port}
              onChange={(e) => setPort(e.target.value)}
              placeholder="Any port"
            />
          </Field>
        </div>
        <Field label="Reason">
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why is this not a real vulnerability in our environment?"
          />
        </Field>
      </div>
    </Dialog>
  );
}
