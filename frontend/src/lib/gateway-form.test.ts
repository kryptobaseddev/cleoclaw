import { beforeEach, describe, expect, it, vi } from "vitest";

import { gatewaysStatusApiV1GatewaysStatusGet } from "@/api/generated/gateways/gateways";

import {
  checkGatewayConnection,
  normalizeGatewayAddress,
  validateGatewayUrl,
} from "./gateway-form";

vi.mock("@/api/generated/gateways/gateways", () => ({
  gatewaysStatusApiV1GatewaysStatusGet: vi.fn(),
}));

const mockedGatewaysStatusApiV1GatewaysStatusGet = vi.mocked(
  gatewaysStatusApiV1GatewaysStatusGet,
);

describe("normalizeGatewayAddress", () => {
  it("prepends http:// to bare IP:port", () => {
    expect(normalizeGatewayAddress("10.0.10.21:18789")).toBe(
      "http://10.0.10.21:18789",
    );
  });

  it("prepends http:// and default port to bare IP", () => {
    expect(normalizeGatewayAddress("10.0.10.21")).toBe(
      "http://10.0.10.21:18789",
    );
  });

  it("prepends https:// to bare FQDN (no port)", () => {
    expect(normalizeGatewayAddress("cleobot.hoskins.fun")).toBe(
      "https://cleobot.hoskins.fun",
    );
  });

  it("prepends http:// to FQDN with explicit port", () => {
    expect(normalizeGatewayAddress("gateway.local:18789")).toBe(
      "http://gateway.local:18789",
    );
  });

  it("treats localhost as IP (adds default port)", () => {
    expect(normalizeGatewayAddress("localhost")).toBe(
      "http://localhost:18789",
    );
  });

  it("passes through full http:// URL", () => {
    expect(normalizeGatewayAddress("http://10.0.10.21:18789")).toBe(
      "http://10.0.10.21:18789",
    );
  });

  it("passes through full https:// URL", () => {
    expect(normalizeGatewayAddress("https://cleobot.hoskins.fun")).toBe(
      "https://cleobot.hoskins.fun",
    );
  });

  it("passes through ws:// URL", () => {
    expect(normalizeGatewayAddress("ws://10.0.10.21:18789")).toBe(
      "ws://10.0.10.21:18789",
    );
  });

  it("trims whitespace", () => {
    expect(normalizeGatewayAddress("  10.0.10.21:18789  ")).toBe(
      "http://10.0.10.21:18789",
    );
  });

  it("returns empty string for empty input", () => {
    expect(normalizeGatewayAddress("")).toBe("");
  });
});

describe("validateGatewayUrl", () => {
  it("accepts bare IP:port", () => {
    expect(validateGatewayUrl("10.0.10.21:18789")).toBeNull();
  });

  it("accepts bare IP (default port assumed)", () => {
    expect(validateGatewayUrl("10.0.10.21")).toBeNull();
  });

  it("accepts bare FQDN", () => {
    expect(validateGatewayUrl("cleobot.hoskins.fun")).toBeNull();
  });

  it("accepts FQDN with port", () => {
    expect(validateGatewayUrl("gateway.example.com:18789")).toBeNull();
  });

  it("accepts http:// URL", () => {
    expect(validateGatewayUrl("http://10.0.10.21:18789")).toBeNull();
  });

  it("accepts https:// URL", () => {
    expect(validateGatewayUrl("https://cleobot.hoskins.fun")).toBeNull();
  });

  it("accepts ws:// URL", () => {
    expect(validateGatewayUrl("ws://localhost:18789")).toBeNull();
  });

  it("accepts wss:// URL", () => {
    expect(validateGatewayUrl("wss://gateway.example.com:8443")).toBeNull();
  });

  it("accepts localhost", () => {
    expect(validateGatewayUrl("localhost")).toBeNull();
  });

  it("rejects empty string", () => {
    expect(validateGatewayUrl("")).toBe("Gateway address is required.");
  });

  it("rejects whitespace only", () => {
    expect(validateGatewayUrl("   ")).toBe("Gateway address is required.");
  });

  it("rejects ftp:// scheme", () => {
    expect(validateGatewayUrl("ftp://gateway.example.com:21")).toBe(
      "Invalid gateway address.",
    );
  });
});

describe("checkGatewayConnection", () => {
  beforeEach(() => {
    mockedGatewaysStatusApiV1GatewaysStatusGet.mockReset();
  });

  it("normalizes address before checking connection", async () => {
    mockedGatewaysStatusApiV1GatewaysStatusGet.mockResolvedValue({
      status: 200,
      data: { connected: true },
    } as never);

    const result = await checkGatewayConnection({
      gatewayUrl: "10.0.10.21:18789",
      gatewayToken: "secret-token",
      gatewayDisableDevicePairing: false,
      gatewayAllowInsecureTls: false,
    });

    expect(mockedGatewaysStatusApiV1GatewaysStatusGet).toHaveBeenCalledWith({
      gateway_url: "http://10.0.10.21:18789",
      gateway_token: "secret-token",
      gateway_disable_device_pairing: false,
      gateway_allow_insecure_tls: false,
    });
    expect(result).toEqual({ ok: true, message: "Gateway reachable." });
  });

  it("normalizes FQDN to https", async () => {
    mockedGatewaysStatusApiV1GatewaysStatusGet.mockResolvedValue({
      status: 200,
      data: { connected: true },
    } as never);

    await checkGatewayConnection({
      gatewayUrl: "cleobot.hoskins.fun",
      gatewayToken: "",
      gatewayDisableDevicePairing: true,
      gatewayAllowInsecureTls: true,
    });

    expect(mockedGatewaysStatusApiV1GatewaysStatusGet).toHaveBeenCalledWith({
      gateway_url: "https://cleobot.hoskins.fun",
      gateway_disable_device_pairing: true,
      gateway_allow_insecure_tls: true,
    });
  });

  it("returns gateway-provided error message when offline", async () => {
    mockedGatewaysStatusApiV1GatewaysStatusGet.mockResolvedValue({
      status: 200,
      data: {
        connected: false,
        error: "missing required scope",
      },
    } as never);

    const result = await checkGatewayConnection({
      gatewayUrl: "ws://gateway.example:18789",
      gatewayToken: "",
      gatewayDisableDevicePairing: false,
      gatewayAllowInsecureTls: false,
    });

    expect(result).toEqual({ ok: false, message: "missing required scope" });
  });
});
