"use client";

import { useCallback, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Copy,
  Loader2,
  Zap,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { customFetch } from "@/api/mutator";
import {
  checkGatewayConnection,
  normalizeGatewayAddress,
  validateGatewayUrl,
} from "@/lib/gateway-form";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type WizardStep = "connect" | "proxy" | "create";

type WizardState = {
  // Step 1: Connect
  gatewayAddress: string;
  gatewayToken: string;
  connectionVerified: boolean;
  connectionError: string | null;
  // Step 2: Proxy
  npmIp: string;
  proxyConfigured: boolean;
  autoConfigStatus: "idle" | "loading" | "success" | "error";
  autoConfigMessage: string | null;
  // Step 3: Create
  gatewayName: string;
  createStatus: "idle" | "loading" | "success" | "error";
  createError: string | null;
};

type GatewayWizardProps = {
  onComplete: (result: {
    gatewayId: string;
    boardId: string | null;
    pairingRequired: boolean;
  }) => void;
  onCancel: () => void;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="ml-2 inline-flex shrink-0 items-center rounded p-1.5 text-app-text-quiet hover:bg-app-surface-muted hover:text-app-text-muted"
      aria-label="Copy"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-app-success" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </button>
  );
}

function StepIndicator({
  steps,
  current,
}: {
  steps: { key: WizardStep; label: string }[];
  current: WizardStep;
}) {
  const currentIndex = steps.findIndex((s) => s.key === current);
  return (
    <div className="flex items-center gap-2">
      {steps.map((step, i) => (
        <div key={step.key} className="flex items-center gap-2">
          {i > 0 ? (
            <div
              className={`h-px w-6 ${i <= currentIndex ? "bg-app-accent" : "bg-app-border"}`}
            />
          ) : null}
          <div className="flex items-center gap-2">
            <span
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${
                i < currentIndex
                  ? "bg-app-success text-white"
                  : i === currentIndex
                    ? "bg-gradient-to-r from-[#2fd9f4] to-[#06b6d4] text-white"
                    : "bg-app-surface-muted text-app-text-quiet"
              }`}
            >
              {i < currentIndex ? <Check className="h-3.5 w-3.5" /> : i + 1}
            </span>
            <span
              className={`text-sm font-medium ${i === currentIndex ? "text-app-text" : "text-app-text-quiet"}`}
            >
              {step.label}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function CodeBlock({ code, label }: { code: string; label?: string }) {
  return (
    <div className="rounded-lg border border-app-border bg-app-surface-muted">
      {label ? (
        <div className="border-b border-app-border px-3 py-1.5 text-xs font-medium text-app-text-quiet">
          {label}
        </div>
      ) : null}
      <div className="flex items-start gap-2 p-3">
        <pre className="flex-1 overflow-x-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-app-text-muted">
          {code}
        </pre>
        <CopyButton text={code} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 1: Connect
// ---------------------------------------------------------------------------

function StepConnect({
  state,
  onChange,
  onVerify,
  onNext,
  verifying,
}: {
  state: WizardState;
  onChange: (updates: Partial<WizardState>) => void;
  onVerify: () => void;
  onNext: () => void;
  verifying: boolean;
}) {
  const [showCustomPort, setShowCustomPort] = useState(false);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-app-text">
          Connect to your OpenClaw gateway
        </h2>
        <p className="mt-1 text-sm text-app-text-quiet">
          Enter the address and auth token of your running OpenClaw gateway.
        </p>
      </div>

      <div className="space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium text-app-text">
            Gateway address <span className="text-app-danger">*</span>
          </label>
          <Input
            value={state.gatewayAddress}
            onChange={(e) =>
              onChange({
                gatewayAddress: e.target.value,
                connectionVerified: false,
                connectionError: null,
              })
            }
            placeholder={showCustomPort ? "10.0.10.21:9000" : "gateway.cleoclaw.com"}
            disabled={verifying}
          />
          <div className="flex items-center justify-between">
            <p className="text-xs text-app-text-quiet">
              Domain name (recommended) or IP address for direct LAN access.
            </p>
            <button
              type="button"
              onClick={() => setShowCustomPort((v) => !v)}
              className="text-xs text-app-text-quiet hover:text-app-text-muted"
            >
              {showCustomPort ? "Hide port option" : "Custom port?"}
            </button>
          </div>
          {showCustomPort ? (
            <p className="text-xs text-app-text-quiet">
              Default port is <code className="font-mono">18789</code>.
              Append <code className="font-mono">:PORT</code> to use a different one (e.g., <code className="font-mono">10.0.10.21:9000</code>).
              Domain names without a port use HTTPS (443) via reverse proxy.
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-app-text">
            Gateway token <span className="text-app-danger">*</span>
          </label>
          <Input
            type="password"
            value={state.gatewayToken}
            onChange={(e) =>
              onChange({
                gatewayToken: e.target.value,
                connectionVerified: false,
                connectionError: null,
              })
            }
            placeholder="Paste your gateway auth token"
            disabled={verifying}
          />
          <div className="rounded-lg border border-app-border bg-app-surface-muted p-3 text-xs text-app-text-muted">
            <p className="font-medium">Where to find your token:</p>
            <p className="mt-1">
              On your OpenClaw server, run:
            </p>
            <div className="mt-1.5 flex items-center">
              <code className="rounded bg-app-surface px-2 py-0.5 font-mono">
                grep token ~/.openclaw/openclaw.json
              </code>
              <CopyButton text='grep token ~/.openclaw/openclaw.json' />
            </div>
            <p className="mt-1.5">
              Look for <code className="rounded bg-app-surface px-1 font-mono">gateway.auth.token</code> value.
              If you haven{"'"}t set one yet, run{" "}
              <code className="rounded bg-app-surface px-1 font-mono">openclaw onboard</code> first.
            </p>
          </div>
        </div>
      </div>

      {state.connectionError ? (
        <p className="text-sm text-app-danger">{state.connectionError}</p>
      ) : null}

      {state.connectionVerified ? (
        <div className="flex items-center gap-2 rounded-lg border border-app-border bg-app-success-soft px-4 py-3 text-sm text-app-success">
          <Check className="h-4 w-4" />
          Gateway is reachable and responding.
        </div>
      ) : null}

      <div className="flex gap-3">
        {state.connectionVerified ? (
          <Button onClick={onNext} className="flex-1">
            Continue
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        ) : (
          <Button
            onClick={onVerify}
            disabled={
              verifying ||
              !state.gatewayAddress.trim() ||
              !state.gatewayToken.trim()
            }
            className="flex-1"
          >
            {verifying ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Checking connection...
              </>
            ) : (
              "Verify connection"
            )}
          </Button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 2: Proxy
// ---------------------------------------------------------------------------

function StepProxy({
  state,
  onChange,
  onAutoConfig,
}: {
  state: WizardState;
  onChange: (updates: Partial<WizardState>) => void;
  onAutoConfig: () => void;
}) {
  const domain =
    state.gatewayAddress
      .replace(/^https?:\/\//, "")
      .split(/[:/]/)[0] || "gateway.cleoclaw.com";
  const isDomain =
    domain.includes(".") && /[a-zA-Z]/.test(domain) && domain !== "localhost";

  const npmConfigNginx = `proxy_set_header X-Forwarded-User ccmc@mission-control;
proxy_read_timeout 86400s;
proxy_buffering off;`;

  const openclawConfigJson = JSON.stringify(
    {
      gateway: {
        bind: "lan",
        trustedProxies: [state.npmIp || "<NPM_IP>", "127.0.0.1"],
        auth: {
          mode: "trusted-proxy",
          trustedProxy: { userHeader: "x-forwarded-user" },
          token: "<keep-your-existing-token>",
        },
        controlUi: {
          allowedOrigins: [
            `https://${isDomain ? domain : "gateway.cleoclaw.com"}`,
            "http://localhost:18789",
          ],
        },
      },
    },
    null,
    2,
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-app-text">
          Reverse proxy configuration
        </h2>
        <p className="mt-1 text-sm text-app-text-quiet">
          Both your CCMC app and OpenClaw gateway need proxy hosts in Nginx Proxy Manager.
          The Advanced tab config below is <strong>required</strong> for real-time streaming.
        </p>
      </div>

      {/* NPM IP input */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-app-text">
          Nginx Proxy Manager IP address
        </label>
        <Input
          value={state.npmIp}
          onChange={(e) => onChange({ npmIp: e.target.value })}
          placeholder="10.0.10.8"
        />
        <p className="text-xs text-app-text-quiet">
          The internal IP of your NPM instance (e.g., 10.0.10.8).
        </p>
      </div>

      {/* CCMC Proxy Host */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-app-text">
          1. CCMC Proxy Host (your Mission Control domain)
        </h3>
        <p className="text-xs text-app-text-quiet">
          This proxy host serves the CCMC webapp (e.g., <code className="font-mono">cleoclaw.yourdomain.com</code>).
        </p>

        <div className="rounded-lg border border-app-border bg-app-surface p-4 backdrop-blur-glass shadow-card">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-app-border">
              <tr>
                <td className="py-2 pr-4 font-medium text-app-text-muted">Forward Port</td>
                <td className="py-2 font-mono">3011 <span className="text-app-text-quiet">(CCMC frontend)</span></td>
              </tr>
              <tr>
                <td className="py-2 pr-4 font-medium text-app-text-muted">Websockets Support</td>
                <td className="py-2 font-semibold text-app-success">ON</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="rounded-lg border border-app-border bg-app-warning-soft p-4">
          <p className="mb-2 text-sm font-semibold text-app-warning">
            Advanced Tab — Required for CCMC
          </p>
          <CodeBlock code={`proxy_read_timeout 86400s;\nproxy_buffering off;`} />
          <p className="mt-2 text-xs text-app-warning">
            Without these settings, board chat and task updates will not stream in real-time.
            The SSE connections will drop with <code>ERR_INCOMPLETE_CHUNKED_ENCODING</code>.
          </p>
        </div>
      </div>

      {/* Gateway Proxy Host — only shown when using a domain */}
      {isDomain ? (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-app-text">
            2. Gateway Proxy Host — <code className="font-mono text-sm">{domain}</code>
          </h3>
          <p className="text-xs text-app-text-quiet">
            Since you{"'"}re connecting to the gateway via a domain name, it also needs a proxy host in NPM.
          </p>

          <div className="rounded-lg border border-app-border bg-app-surface p-4 backdrop-blur-glass shadow-card">
            <table className="w-full text-sm">
              <tbody className="divide-y divide-app-border">
                <tr>
                  <td className="py-2 pr-4 font-medium text-app-text-muted">Domain Names</td>
                  <td className="py-2 font-mono text-app-text">{domain}</td>
                </tr>
                <tr>
                  <td className="py-2 pr-4 font-medium text-app-text-muted">Forward Port</td>
                  <td className="py-2 font-mono">18789</td>
                </tr>
                <tr>
                  <td className="py-2 pr-4 font-medium text-app-text-muted">Websockets Support</td>
                  <td className="py-2 font-semibold text-app-success">ON</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="rounded-lg border border-app-border bg-app-warning-soft p-4">
            <p className="mb-2 text-sm font-semibold text-app-warning">
              Advanced Tab — Required
            </p>
            <CodeBlock code={npmConfigNginx} />
            <p className="mt-2 text-xs text-app-warning">
              <code>X-Forwarded-User</code> identifies CCMC for trusted-proxy auth.
              Timeout and buffering settings keep connections alive.
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-app-border bg-app-success-soft p-3 text-sm text-app-success">
          <Check className="mr-2 inline h-4 w-4" />
          Direct IP connection — no gateway proxy host needed. CCMC connects to{" "}
          <code className="font-mono">{state.gatewayAddress}</code> directly.
        </div>
      )}

      {/* SSL for both */}
      <div className="rounded-lg border border-app-border bg-app-surface p-4 backdrop-blur-glass shadow-card">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-app-text-quiet">
          SSL Tab (both proxy hosts)
        </p>
        <div className="flex flex-wrap gap-2 text-xs">
          {["Force SSL", "HTTP/2 Support", "HSTS Enabled", "HSTS Subdomains"].map(
            (s) => (
              <span
                key={s}
                className="rounded-full bg-app-success-soft px-2.5 py-1 font-medium text-app-success"
              >
                {s} — ON
              </span>
            ),
          )}
        </div>
        <p className="mt-2 text-xs text-app-text-quiet">
          Use Let{"'"}s Encrypt for SSL certificates on both proxy hosts.
        </p>
      </div>

      {/* OpenClaw Config */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-app-text">
          2. Configure trusted-proxy auth on OpenClaw
        </h3>

        {state.npmIp.trim() ? (
          <div className="rounded-lg border border-app-border bg-app-warning-soft p-4">
            <div className="flex items-start gap-3">
              <Zap className="mt-0.5 h-5 w-5 shrink-0 text-app-warning" />
              <div className="flex-1">
                <p className="text-sm font-medium text-app-warning">
                  Auto-configure with one click
                </p>
                <p className="mt-1 text-xs text-app-text-muted">
                  CCMC can apply the trusted-proxy config to your gateway
                  automatically. This updates{" "}
                  <code className="font-mono">~/.openclaw/openclaw.json</code>{" "}
                  via the gateway API.
                </p>
                <Button
                  size="sm"
                  className="mt-3"
                  onClick={onAutoConfig}
                  disabled={state.autoConfigStatus === "loading"}
                >
                  {state.autoConfigStatus === "loading" ? (
                    <>
                      <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                      Applying...
                    </>
                  ) : state.autoConfigStatus === "success" ? (
                    <>
                      <Check className="mr-2 h-3.5 w-3.5" />
                      Applied successfully
                    </>
                  ) : (
                    <>
                      <Zap className="mr-2 h-3.5 w-3.5" />
                      Apply trusted-proxy config
                    </>
                  )}
                </Button>
                {state.autoConfigMessage ? (
                  <p
                    className={`mt-2 text-xs ${
                      state.autoConfigStatus === "error"
                        ? "text-app-danger"
                        : "text-app-success"
                    }`}
                  >
                    {state.autoConfigMessage}
                  </p>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}

        <details className="group">
          <summary className="cursor-pointer text-sm text-app-text-quiet hover:text-app-text-muted">
            Or apply manually — copy this config
          </summary>
          <div className="mt-2">
            <CodeBlock
              code={openclawConfigJson}
              label="~/.openclaw/openclaw.json (gateway section)"
            />
          </div>
        </details>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 3: Create
// ---------------------------------------------------------------------------

function StepCreate({
  state,
  onChange,
}: {
  state: WizardState;
  onChange: (updates: Partial<WizardState>) => void;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-app-text">
          Name your gateway
        </h2>
        <p className="mt-1 text-sm text-app-text-quiet">
          Give your gateway a friendly name. CCMC will create a default board and agent automatically.
        </p>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium text-app-text">
          Gateway name <span className="text-app-danger">*</span>
        </label>
        <Input
          value={state.gatewayName}
          onChange={(e) => onChange({ gatewayName: e.target.value })}
          placeholder="Production Gateway"
          autoFocus
        />
      </div>

      <div className="rounded-lg border border-app-border bg-app-surface-muted p-4 backdrop-blur-glass shadow-card">
        <p className="text-sm font-medium text-app-text">What happens next:</p>
        <ul className="mt-2 space-y-1.5 text-sm text-app-text-muted">
          <li className="flex items-start gap-2">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-app-success" />
            Gateway registered in Mission Control
          </li>
          <li className="flex items-start gap-2">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-app-success" />
            MC Gateway Agent created on OpenClaw
          </li>
          <li className="flex items-start gap-2">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-app-success" />
            Default {'"'}General{'"'} board created with lead agent
          </li>
          <li className="flex items-start gap-2">
            <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-app-text-quiet" />
            You{"'"}ll be taken to your new board
          </li>
        </ul>
      </div>

      {state.createError ? (
        <p className="text-sm text-app-danger">{state.createError}</p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Wizard
// ---------------------------------------------------------------------------

const STEPS: { key: WizardStep; label: string }[] = [
  { key: "connect", label: "Connect" },
  { key: "proxy", label: "Proxy" },
  { key: "create", label: "Create" },
];

export function GatewayWizard({ onComplete, onCancel }: GatewayWizardProps) {
  const [step, setStep] = useState<WizardStep>("connect");
  const [verifying, setVerifying] = useState(false);
  const [creating, setCreating] = useState(false);
  const [state, setState] = useState<WizardState>({
    gatewayAddress: "",
    gatewayToken: "",
    connectionVerified: false,
    connectionError: null,
    npmIp: "",
    proxyConfigured: false,
    autoConfigStatus: "idle",
    autoConfigMessage: null,
    gatewayName: "",
    createStatus: "idle",
    createError: null,
  });

  const update = useCallback(
    (updates: Partial<WizardState>) =>
      setState((prev) => ({ ...prev, ...updates })),
    [],
  );

  // Step 1: Verify connection
  const handleVerify = async () => {
    const validation = validateGatewayUrl(state.gatewayAddress);
    if (validation) {
      update({ connectionError: validation });
      return;
    }
    setVerifying(true);
    update({ connectionError: null });
    const { ok, message } = await checkGatewayConnection({
      gatewayUrl: state.gatewayAddress,
      gatewayToken: state.gatewayToken,
      gatewayDisableDevicePairing: false,
      gatewayAllowInsecureTls: false,
    });
    setVerifying(false);
    if (ok) {
      update({ connectionVerified: true, connectionError: null });
    } else {
      update({ connectionVerified: false, connectionError: message });
    }
  };

  // Step 2: Auto-configure trusted-proxy
  const handleAutoConfig = async () => {
    update({ autoConfigStatus: "loading", autoConfigMessage: null });
    try {
      const normalizedUrl = normalizeGatewayAddress(state.gatewayAddress);
      const domain = state.gatewayAddress
        .replace(/^https?:\/\//, "")
        .split(/[:/]/)[0];
      const res = await customFetch<{ data: { ok: boolean; message: string } }>(
        "/api/v1/gateways/configure-trusted-proxy",
        {
          method: "POST",
          body: JSON.stringify({
            gateway_url: normalizedUrl,
            gateway_token: state.gatewayToken,
            npm_ip: state.npmIp,
            gateway_fqdn: domain.includes(".") ? domain : null,
          }),
        },
      );
      const data = res.data;
      if (data.ok) {
        update({
          autoConfigStatus: "success",
          autoConfigMessage: data.message,
          proxyConfigured: true,
        });
      } else {
        update({
          autoConfigStatus: "error",
          autoConfigMessage: data.message || "Failed to configure.",
        });
      }
    } catch (err) {
      update({
        autoConfigStatus: "error",
        autoConfigMessage:
          err instanceof Error ? err.message : "Network error.",
      });
    }
  };

  // Step 3: Create gateway
  const handleCreate = async () => {
    if (!state.gatewayName.trim()) {
      update({ createError: "Gateway name is required." });
      return;
    }
    setCreating(true);
    update({ createError: null });

    try {
      const res = await customFetch<{
        data: {
          gateway_id: string;
          board_id: string | null;
          agent_id: string | null;
          pairing_required: boolean;
        };
      }>("/api/v1/gateways", {
        method: "POST",
        body: JSON.stringify({
          name: state.gatewayName.trim(),
          url: normalizeGatewayAddress(state.gatewayAddress),
          token: state.gatewayToken.trim() || null,
          disable_device_pairing: false,
          workspace_root: "~/.openclaw",
          allow_insecure_tls: false,
        }),
      });

      const data = res.data;
      setCreating(false);
      onComplete({
        gatewayId: data.gateway_id,
        boardId: data.board_id ?? null,
        pairingRequired: data.pairing_required ?? false,
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Network error.";
      update({ createError: message });
      setCreating(false);
    }
  };

  // Navigation
  const canNext =
    step === "connect"
      ? state.connectionVerified
      : step === "proxy"
        ? true // proxy step is optional
        : Boolean(state.gatewayName.trim());

  const handleNext = () => {
    if (step === "connect") setStep("proxy");
    else if (step === "proxy") setStep("create");
    else if (step === "create") handleCreate();
  };

  const handleBack = () => {
    if (step === "proxy") setStep("connect");
    else if (step === "create") setStep("proxy");
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <StepIndicator steps={STEPS} current={step} />

      <div className="rounded-xl border border-app-border bg-app-surface p-6 backdrop-blur-glass shadow-card">
        {step === "connect" ? (
          <StepConnect
            state={state}
            onChange={update}
            onVerify={handleVerify}
            onNext={() => setStep("proxy")}
            verifying={verifying}
          />
        ) : step === "proxy" ? (
          <StepProxy
            state={state}
            onChange={update}
            onAutoConfig={handleAutoConfig}
          />
        ) : (
          <StepCreate state={state} onChange={update} />
        )}
      </div>

      <div className="flex items-center justify-between">
        <Button
          type="button"
          variant="ghost"
          onClick={step === "connect" ? onCancel : handleBack}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {step === "connect" ? "Cancel" : "Back"}
        </Button>

        {step === "proxy" ? (
          <Button onClick={handleNext}>
            Continue
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        ) : step === "create" ? (
          <Button
            onClick={handleNext}
            disabled={!canNext || creating}
          >
            {creating ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Creating gateway...
              </>
            ) : (
              <>
                Create gateway
                <Check className="ml-2 h-4 w-4" />
              </>
            )}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
