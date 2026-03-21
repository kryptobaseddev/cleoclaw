import { gatewaysStatusApiV1GatewaysStatusGet } from "@/api/generated/gateways/gateways";

export const DEFAULT_WORKSPACE_ROOT = "~/.openclaw";

export type GatewayCheckStatus = "idle" | "checking" | "success" | "error";

/**
 * Returns true only when the URL string contains an explicit ":port" segment.
 *
 * JavaScript's URL API sets `.port` to "" for *both* an omitted port and a
 * port that equals the scheme's default (e.g. 443 for wss:). We therefore
 * inspect the raw host+port token from the URL string instead.
 */
function hasExplicitPort(urlString: string): boolean {
  try {
    // Extract the authority portion (between // and the first / ? or #)
    const withoutScheme = urlString.slice(urlString.indexOf("//") + 2);
    const authority = withoutScheme.split(/[/?#]/)[0];
    if (!authority) {
      return false;
    }

    // authority may be:
    // - host[:port]
    // - [ipv6][:port]
    // - userinfo@host[:port]
    // - userinfo@[ipv6][:port]
    const atIndex = authority.lastIndexOf("@");
    const hostPort = atIndex === -1 ? authority : authority.slice(atIndex + 1);

    let portSegment = "";
    if (hostPort.startsWith("[")) {
      const closingBracketIndex = hostPort.indexOf("]");
      if (closingBracketIndex === -1) {
        return false;
      }
      portSegment = hostPort.slice(closingBracketIndex + 1);
    } else {
      const lastColonIndex = hostPort.lastIndexOf(":");
      if (lastColonIndex === -1) {
        return false;
      }
      portSegment = hostPort.slice(lastColonIndex);
    }

    if (!portSegment.startsWith(":") || !/^:\d+$/.test(portSegment)) {
      return false;
    }

    const port = Number.parseInt(portSegment.slice(1), 10);
    return Number.isInteger(port) && port >= 0 && port <= 65535;
  } catch {
    return false;
  }
}

/**
 * Detect whether a bare hostname looks like a domain name (FQDN) vs an IP.
 * FQDNs go through a reverse proxy (Nginx) on port 443 — no explicit port needed.
 * IPs connect directly to the OpenClaw gateway on port 18789.
 */
function looksLikeDomain(host: string): boolean {
  // IPv4 addresses: digits and dots only
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) return false;
  // IPv6 addresses
  if (host.startsWith("[") || host.includes("::")) return false;
  // localhost
  if (host === "localhost") return false;
  // Has a dot and contains letters — it's a domain
  return host.includes(".") && /[a-zA-Z]/.test(host);
}

/**
 * Normalize a gateway address into a full URL.
 *
 * Accepts:
 * - IP:port (10.0.10.21:18789)        → http://10.0.10.21:18789
 * - IP only (10.0.10.21)              → http://10.0.10.21:18789
 * - FQDN (cleobot.hoskins.fun)        → https://cleobot.hoskins.fun
 * - FQDN:port (gateway.local:18789)   → http://gateway.local:18789
 * - Full URL (http://..., ws://...)    → as-is
 *
 * The SDK derives both HTTP and WS URLs from whatever scheme is stored,
 * so the user never needs to think about transport protocols.
 */
export function normalizeGatewayAddress(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";

  // Already has a recognized scheme — pass through
  if (/^(https?|wss?):\/\//i.test(trimmed)) {
    return trimmed;
  }

  // Reject unrecognized schemes (ftp://, etc.)
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed)) {
    return trimmed; // let validation catch the bad protocol
  }

  // Check if the input has an explicit port
  const hasPort = hasExplicitPort(`http://${trimmed}`);

  if (hasPort) {
    // Has a port — connect directly via HTTP (LAN/direct access)
    return `http://${trimmed}`;
  }

  // No port — determine scheme based on whether it's a domain or IP
  const host = trimmed.split(/[/?#]/)[0];

  if (looksLikeDomain(host)) {
    // FQDN without port → HTTPS (behind reverse proxy like Nginx)
    return `https://${trimmed}`;
  }

  // IP or localhost without port → HTTP with default OpenClaw port
  return `http://${trimmed}:18789`;
}

export const validateGatewayUrl = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) return "Gateway address is required.";

  const normalized = normalizeGatewayAddress(trimmed);

  try {
    const url = new URL(normalized);
    if (!["ws:", "wss:", "http:", "https:"].includes(url.protocol)) {
      return "Invalid gateway address.";
    }
    // FQDNs behind reverse proxy don't need explicit ports (443 implied)
    // IPs and localhost always get a port from normalizeGatewayAddress
    return null;
  } catch {
    return "Enter a valid gateway address (e.g. 10.0.10.21:18789 or gateway.example.com).";
  }
};

export async function checkGatewayConnection(params: {
  gatewayUrl: string;
  gatewayToken: string;
  gatewayDisableDevicePairing: boolean;
  gatewayAllowInsecureTls: boolean;
}): Promise<{ ok: boolean; message: string }> {
  try {
    const requestParams: {
      gateway_url: string;
      gateway_token?: string;
      gateway_disable_device_pairing: boolean;
      gateway_allow_insecure_tls: boolean;
    } = {
      gateway_url: normalizeGatewayAddress(params.gatewayUrl),
      gateway_disable_device_pairing: params.gatewayDisableDevicePairing,
      gateway_allow_insecure_tls: params.gatewayAllowInsecureTls,
    };
    if (params.gatewayToken.trim()) {
      requestParams.gateway_token = params.gatewayToken.trim();
    }

    const response = await gatewaysStatusApiV1GatewaysStatusGet(requestParams);
    if (response.status !== 200) {
      return { ok: false, message: "Unable to reach gateway." };
    }
    const data = response.data;
    if (!data.connected) {
      return { ok: false, message: data.error ?? "Unable to reach gateway." };
    }
    return { ok: true, message: "Gateway reachable." };
  } catch (error) {
    return {
      ok: false,
      message:
        error instanceof Error ? error.message : "Unable to reach gateway.",
    };
  }
}
