"use client";

import { useState } from "react";
import { Check, ChevronDown, ChevronRight, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";

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
      className="ml-2 inline-flex items-center rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-600"
      aria-label="Copy"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-emerald-500" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </button>
  );
}

function CollapsibleSection({
  title,
  step,
  children,
  defaultOpen = false,
}: {
  title: string;
  step: number;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left text-sm font-medium text-slate-900 hover:bg-slate-50"
      >
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
          {step}
        </span>
        <span className="flex-1">{title}</span>
        {open ? (
          <ChevronDown className="h-4 w-4 text-slate-400" />
        ) : (
          <ChevronRight className="h-4 w-4 text-slate-400" />
        )}
      </button>
      {open ? (
        <div className="border-t border-slate-100 px-4 py-3 text-sm text-slate-600">
          {children}
        </div>
      ) : null}
    </div>
  );
}

type GatewaySetupGuideProps = {
  gatewayAddress?: string;
};

export function GatewaySetupGuide({
  gatewayAddress,
}: GatewaySetupGuideProps) {
  const [expanded, setExpanded] = useState(false);

  // Derive display values from the address
  const domain = gatewayAddress?.replace(/^https?:\/\//, "").split(/[:/]/)[0] || "gateway.cleoclaw.com";
  const isDirectIp = /^\d{1,3}(\.\d{1,3}){3}$/.test(domain);

  return (
    <div className="space-y-3">
      <Button
        type="button"
        variant="ghost"
        className="w-full justify-start text-sm text-slate-500 hover:text-slate-700"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? (
          <ChevronDown className="mr-2 h-4 w-4" />
        ) : (
          <ChevronRight className="mr-2 h-4 w-4" />
        )}
        Gateway setup prerequisites
      </Button>

      {expanded ? (
        <div className="space-y-2">
          <CollapsibleSection step={1} title="Install OpenClaw on your server">
            <div className="space-y-2">
              <p>Install and run the onboarding wizard:</p>
              <div className="flex items-center rounded bg-slate-50 px-3 py-2">
                <code className="flex-1 font-mono text-xs">
                  npm install -g openclaw && openclaw onboard
                </code>
                <CopyButton text="npm install -g openclaw && openclaw onboard" />
              </div>
              <p className="text-xs text-slate-500">
                This creates <code>~/.openclaw/openclaw.json</code> with your gateway config and auth token.
              </p>
            </div>
          </CollapsibleSection>

          <CollapsibleSection step={2} title="Configure Nginx Proxy Manager">
            <div className="space-y-3">
              <p>Create a proxy host in NPM with these settings:</p>

              <div className="space-y-1">
                <p className="font-medium text-slate-800">Details tab:</p>
                <table className="w-full text-xs">
                  <tbody>
                    <tr className="border-b border-slate-100">
                      <td className="py-1.5 pr-3 font-medium text-slate-700">Domain Names</td>
                      <td className="py-1.5 font-mono">{isDirectIp ? "gateway.cleoclaw.com" : domain}</td>
                    </tr>
                    <tr className="border-b border-slate-100">
                      <td className="py-1.5 pr-3 font-medium text-slate-700">Scheme</td>
                      <td className="py-1.5">http</td>
                    </tr>
                    <tr className="border-b border-slate-100">
                      <td className="py-1.5 pr-3 font-medium text-slate-700">Forward Hostname / IP</td>
                      <td className="py-1.5 font-mono">{"<your OpenClaw server IP>"}</td>
                    </tr>
                    <tr className="border-b border-slate-100">
                      <td className="py-1.5 pr-3 font-medium text-slate-700">Forward Port</td>
                      <td className="py-1.5 font-mono">18789</td>
                    </tr>
                    <tr className="border-b border-slate-100">
                      <td className="py-1.5 pr-3 font-medium text-slate-700">Cache Assets</td>
                      <td className="py-1.5">OFF</td>
                    </tr>
                    <tr className="border-b border-slate-100">
                      <td className="py-1.5 pr-3 font-medium text-slate-700">Block Common Exploits</td>
                      <td className="py-1.5">ON</td>
                    </tr>
                    <tr>
                      <td className="py-1.5 pr-3 font-medium text-slate-700">Websockets Support</td>
                      <td className="py-1.5 font-medium text-emerald-600">ON (required)</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="space-y-1">
                <p className="font-medium text-slate-800">SSL tab:</p>
                <table className="w-full text-xs">
                  <tbody>
                    <tr className="border-b border-slate-100">
                      <td className="py-1.5 pr-3 font-medium text-slate-700">SSL Certificate</td>
                      <td className="py-1.5">Request new Let{"'"}s Encrypt certificate</td>
                    </tr>
                    <tr className="border-b border-slate-100">
                      <td className="py-1.5 pr-3 font-medium text-slate-700">Force SSL</td>
                      <td className="py-1.5">ON</td>
                    </tr>
                    <tr className="border-b border-slate-100">
                      <td className="py-1.5 pr-3 font-medium text-slate-700">HTTP/2 Support</td>
                      <td className="py-1.5">ON</td>
                    </tr>
                    <tr className="border-b border-slate-100">
                      <td className="py-1.5 pr-3 font-medium text-slate-700">HSTS Enabled</td>
                      <td className="py-1.5">ON</td>
                    </tr>
                    <tr>
                      <td className="py-1.5 pr-3 font-medium text-slate-700">HSTS Subdomains</td>
                      <td className="py-1.5">ON</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="space-y-1">
                <p className="font-medium text-slate-800">Advanced tab — Custom Nginx Configuration:</p>
                <div className="flex items-center rounded bg-slate-50 px-3 py-2">
                  <code className="flex-1 font-mono text-xs">
                    proxy_set_header X-Forwarded-User ccmc@mission-control;{"\n"}proxy_read_timeout 86400s;{"\n"}proxy_buffering off;
                  </code>
                  <CopyButton text={"proxy_set_header X-Forwarded-User ccmc@mission-control;\nproxy_read_timeout 86400s;\nproxy_buffering off;"} />
                </div>
              </div>
            </div>
          </CollapsibleSection>

          <CollapsibleSection step={3} title="Configure trusted-proxy auth on OpenClaw">
            <div className="space-y-2">
              <p>
                Update <code>~/.openclaw/openclaw.json</code> on your gateway server:
              </p>
              <div className="rounded bg-slate-50 p-3">
                <pre className="overflow-x-auto font-mono text-xs leading-relaxed">
{`{
  "gateway": {
    "bind": "lan",
    "trustedProxies": ["<NPM_IP>", "127.0.0.1"],
    "auth": {
      "mode": "trusted-proxy",
      "trustedProxy": {
        "userHeader": "x-forwarded-user"
      },
      "token": "<your-existing-token>"
    },
    "controlUi": {
      "allowedOrigins": [
        "https://${isDirectIp ? "gateway.cleoclaw.com" : domain}",
        "http://<GATEWAY_IP>:18789"
      ]
    }
  }
}`}
                </pre>
              </div>
              <p className="text-xs text-slate-500">
                Replace <code>{"<NPM_IP>"}</code> with your Nginx Proxy Manager IP address.
                The gateway reloads automatically after saving.
              </p>
            </div>
          </CollapsibleSection>

          <CollapsibleSection step={4} title="Enter gateway details above">
            <div className="space-y-2">
              <p>Fill in the form above with:</p>
              <ul className="list-inside list-disc space-y-1">
                <li>
                  <strong>Gateway name</strong> — a friendly label (e.g., {'"'}Production Gateway{'"'})
                </li>
                <li>
                  <strong>Gateway address</strong> — your domain name (e.g., <code>{isDirectIp ? "gateway.cleoclaw.com" : domain}</code>)
                  {!isDirectIp ? null : " or direct IP:port for LAN-only access"}
                </li>
                <li>
                  <strong>Gateway token</strong> — from <code>~/.openclaw/openclaw.json</code> → <code>gateway.auth.token</code>
                </li>
              </ul>
            </div>
          </CollapsibleSection>
        </div>
      ) : null}
    </div>
  );
}
