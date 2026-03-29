"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, Loader2 } from "lucide-react";

import { customFetch } from "@/api/mutator";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type PairingApprovalModalProps = {
  gatewayId: string;
  gatewayAddress: string;
  onComplete: (boardId: string | null) => void;
  onCancel: () => void;
};

export function PairingApprovalModal({
  gatewayId,
  gatewayAddress,
  onComplete,
  onCancel,
}: PairingApprovalModalProps) {
  const [polling, setPolling] = useState(true);
  const [copied, setCopied] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const pollSetup = useCallback(async () => {
    try {
      const res = await customFetch<{
        data: { pairing_required: boolean; board_id: string | null };
      }>(`/api/v1/gateways/${gatewayId}/complete-setup`, {
        method: "POST",
      });
      if (!res.data.pairing_required) {
        setPolling(false);
        if (intervalRef.current) clearInterval(intervalRef.current);
        onComplete(res.data.board_id ?? null);
      }
    } catch {
      // Silently retry on next interval
    }
  }, [gatewayId, onComplete]);

  useEffect(() => {
    intervalRef.current = setInterval(pollSetup, 3000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [pollSetup]);

  const handleCopy = () => {
    navigator.clipboard.writeText("openclaw device list");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onCancel(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Approve device pairing</DialogTitle>
          <DialogDescription>
            Your gateway at <strong>{gatewayAddress}</strong> requires a one-time device pairing approval.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
            <p className="mb-3 font-medium text-slate-900">
              On your gateway server, approve the pending pairing request:
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded bg-slate-100 px-3 py-2 font-mono text-xs">
                openclaw device list
              </code>
              <button
                type="button"
                onClick={handleCopy}
                className="rounded-md p-2 text-slate-500 hover:bg-slate-200 hover:text-slate-700"
                aria-label="Copy command"
              >
                {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              Then approve the pending request with{" "}
              <code className="rounded bg-slate-100 px-1 py-0.5 font-mono">
                openclaw device approve &lt;request-id&gt;
              </code>
              . You can also approve via Telegram if configured.
            </p>
          </div>

          {polling ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Waiting for pairing approval...</span>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
