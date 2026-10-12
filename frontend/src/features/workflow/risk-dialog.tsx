import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Dialog } from "@/components/ui/overlay";
import { Button, Field, Input, Textarea } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { AppSettings } from "@/lib/types";

function isoInDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export const useAppSettings = () =>
  useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<AppSettings>("/settings"),
    staleTime: 300_000,
  });

/** Ask an approver to accept the risk of one or more findings until a date. */
export function RiskRequestDialog({
  findingIds,
  open,
  onOpenChange,
  onDone,
}: {
  findingIds: number[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone?: () => void;
}) {
  const qc = useQueryClient();
  const { data: settings } = useAppSettings();
  const maxDays = settings?.risk_max_days ?? 365;
  const [justification, setJustification] = useState("");
  const [expires, setExpires] = useState(isoInDays(Math.min(90, maxDays)));

  const submit = useMutation({
    mutationFn: () =>
      api.post<{ created: number }>("/risk-acceptances", {
        finding_ids: findingIds,
        justification,
        expires_at: expires,
      }),
    onSuccess: (r) => {
      toast.success(
        r.created === 1 ? "Risk acceptance requested" : `Requested acceptance for ${r.created} findings`,
      );
      qc.invalidateQueries({ queryKey: ["risk"] });
      qc.invalidateQueries({ queryKey: ["finding"] });
      setJustification("");
      onOpenChange(false);
      onDone?.();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Request risk acceptance"
      description={
        findingIds.length === 1
          ? "An approver reviews the request. The finding stays open until it is approved."
          : `${findingIds.length} findings. An approver reviews each one; they stay open until approved.`
      }
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!justification.trim() || !expires}
            loading={submit.isPending}
            onClick={() => submit.mutate()}
          >
            Send request
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field
          label="Business justification"
          hint="Compensating controls, owner, and why fixing now is not possible."
        >
          <Textarea
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
            placeholder="e.g. Legacy core-banking host, isolated VLAN, vendor patch due Q3. WAF rule 4102 blocks the exploit path."
            className="min-h-28"
          />
        </Field>
        <Field
          label="Accept until"
          hint={`At most ${maxDays} days. The finding reopens automatically on this date.`}
        >
          <Input
            type="date"
            value={expires}
            min={isoInDays(1)}
            max={isoInDays(maxDays)}
            onChange={(e) => setExpires(e.target.value)}
          />
        </Field>
      </div>
    </Dialog>
  );
}
