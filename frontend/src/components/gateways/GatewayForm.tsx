import { type FormEvent, useState } from "react";
import { Info } from "lucide-react";

import type { GatewayCheckStatus } from "@/lib/gateway-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function InfoHint({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative ml-1 inline-block align-middle">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 hover:text-slate-600"
        aria-label="More info"
      >
        <Info className="h-3.5 w-3.5" />
      </button>
      {open ? (
        <span className="absolute bottom-full left-1/2 z-50 mb-2 w-64 -translate-x-1/2 rounded-lg border border-slate-200 bg-white p-3 text-xs font-normal leading-relaxed text-slate-600 shadow-lg">
          {text}
        </span>
      ) : null}
    </span>
  );
}

type GatewayFormProps = {
  name: string;
  gatewayUrl: string;
  gatewayToken: string;
  disableDevicePairing: boolean;
  workspaceRoot: string;
  allowInsecureTls: boolean;
  gatewayUrlError: string | null;
  gatewayCheckStatus: GatewayCheckStatus;
  gatewayCheckMessage: string | null;
  errorMessage: string | null;
  isLoading: boolean;
  canSubmit: boolean;
  workspaceRootPlaceholder: string;
  cancelLabel: string;
  submitLabel: string;
  submitBusyLabel: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
  onNameChange: (next: string) => void;
  onGatewayUrlChange: (next: string) => void;
  onGatewayTokenChange: (next: string) => void;
  onDisableDevicePairingChange: (next: boolean) => void;
  onWorkspaceRootChange: (next: string) => void;
  onAllowInsecureTlsChange: (next: boolean) => void;
};

export function GatewayForm({
  name,
  gatewayUrl,
  gatewayToken,
  disableDevicePairing,
  workspaceRoot,
  allowInsecureTls,
  gatewayUrlError,
  gatewayCheckStatus,
  gatewayCheckMessage,
  errorMessage,
  isLoading,
  canSubmit,
  workspaceRootPlaceholder,
  cancelLabel,
  submitLabel,
  submitBusyLabel,
  onSubmit,
  onCancel,
  onNameChange,
  onGatewayUrlChange,
  onGatewayTokenChange,
  onDisableDevicePairingChange,
  onWorkspaceRootChange,
  onAllowInsecureTlsChange,
}: GatewayFormProps) {
  return (
    <form
      onSubmit={onSubmit}
      className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="space-y-2">
        <label className="text-sm font-medium text-slate-900">
          Gateway name <span className="text-red-500">*</span>
        </label>
        <Input
          value={name}
          onChange={(event) => onNameChange(event.target.value)}
          placeholder="Primary gateway"
          disabled={isLoading}
        />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-900">
            Gateway address <span className="text-red-500">*</span>
            <InfoHint text="Enter the IP or domain of your OpenClaw gateway. Mission Control handles the protocol automatically. Examples: 10.0.10.21:18789 (direct LAN), 10.0.10.21 (default port 18789 assumed), cleobot.hoskins.fun (HTTPS through reverse proxy), gateway.local:18789 (direct with explicit port)." />
          </label>
          <div className="relative">
            <Input
              value={gatewayUrl}
              onChange={(event) => onGatewayUrlChange(event.target.value)}
              placeholder="10.0.10.21:18789"
              disabled={isLoading}
              className={gatewayUrlError ? "border-red-500" : undefined}
            />
          </div>
          {gatewayUrlError ? (
            <p className="text-xs text-red-500">{gatewayUrlError}</p>
          ) : gatewayCheckStatus === "error" && gatewayCheckMessage ? (
            <p className="text-xs text-red-500">{gatewayCheckMessage}</p>
          ) : null}
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-900">
            Gateway token
            <InfoHint text="The bearer token used to authenticate with the gateway. Found in your OpenClaw config at gateway.auth.token or the OPENCLAW_GATEWAY_TOKEN environment variable. Required when gateway auth mode is 'token'." />
          </label>
          <Input
            value={gatewayToken}
            onChange={(event) => onGatewayTokenChange(event.target.value)}
            placeholder="Bearer token"
            disabled={isLoading}
          />
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-900">
            Workspace root <span className="text-red-500">*</span>
            <InfoHint text="The absolute path on the gateway server where OpenClaw stores its configuration, agents, and session data. Usually ~/.openclaw or /root/.openclaw on Linux." />
          </label>
          <Input
            value={workspaceRoot}
            onChange={(event) => onWorkspaceRootChange(event.target.value)}
            placeholder={workspaceRootPlaceholder}
            disabled={isLoading}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-900">
            Disable device pairing
            <InfoHint text="When OFF (default), Mission Control authenticates via cryptographic device pairing (ECDSA signatures). The gateway must approve this device on first connection. When ON, uses control-UI mode instead, which requires HTTPS or localhost and skips device-level security. Leave OFF unless you know your gateway requires control-UI mode." />
          </label>
          <label className="flex h-10 items-center gap-3 px-1 text-sm text-slate-900">
            <button
              type="button"
              role="switch"
              aria-checked={disableDevicePairing}
              aria-label="Disable device pairing"
              onClick={() =>
                onDisableDevicePairingChange(!disableDevicePairing)
              }
              disabled={isLoading}
              className={`inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition ${
                disableDevicePairing
                  ? "border-emerald-600 bg-emerald-600"
                  : "border-slate-300 bg-slate-200"
              } ${isLoading ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
            >
              <span
                className={`inline-block h-5 w-5 rounded-full bg-white shadow-sm transition ${
                  disableDevicePairing ? "translate-x-5" : "translate-x-0.5"
                }`}
              />
            </button>
          </label>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium text-slate-900">
          Allow self-signed TLS certificates
          <InfoHint text="Enable this only if your gateway uses wss:// (WebSocket over TLS) with a self-signed certificate. This skips certificate verification for that gateway connection. Leave OFF for plain HTTP/WS connections or gateways with valid TLS certificates." />
        </label>
        <label className="flex h-10 items-center gap-3 px-1 text-sm text-slate-900">
          <button
            type="button"
            role="switch"
            aria-checked={allowInsecureTls}
            aria-label="Allow self-signed TLS certificates"
            onClick={() => onAllowInsecureTlsChange(!allowInsecureTls)}
            disabled={isLoading}
            className={`inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition ${
              allowInsecureTls
                ? "border-emerald-600 bg-emerald-600"
                : "border-slate-300 bg-slate-200"
            } ${isLoading ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
          >
            <span
              className={`inline-block h-5 w-5 rounded-full bg-white shadow-sm transition ${
                allowInsecureTls ? "translate-x-5" : "translate-x-0.5"
              }`}
            />
          </button>
        </label>
      </div>

      {errorMessage ? (
        <p className="text-sm text-red-500">{errorMessage}</p>
      ) : null}

      <div className="flex justify-end gap-3">
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={isLoading}
        >
          {cancelLabel}
        </Button>
        <Button type="submit" disabled={isLoading || !canSubmit}>
          {isLoading ? submitBusyLabel : submitLabel}
        </Button>
      </div>
    </form>
  );
}
