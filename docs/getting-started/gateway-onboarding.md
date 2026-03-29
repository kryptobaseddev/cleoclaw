# Gateway Onboarding Guide

Complete setup guide for connecting CleoClaw Mission Control (CCMC) to an OpenClaw gateway.

## Prerequisites

Before creating a gateway in CCMC, you need:

1. **OpenClaw installed and running** on a server (LXC, VM, or bare metal)
2. **Nginx Proxy Manager (NPM)** configured as a reverse proxy (recommended)
3. **A domain name** pointing to your NPM instance (e.g., `gateway.cleoclaw.com`)

## Step 1: Install and Onboard OpenClaw

On your gateway server:

```bash
# Install OpenClaw
npm install -g openclaw

# Run the onboarding wizard
openclaw onboard

# This creates ~/.openclaw/openclaw.json with your gateway config
# Note: the wizard will set up auth token, models, and channels
```

After onboarding, verify the gateway is running:

```bash
openclaw gateway status --deep
```

Note your **gateway auth token** — you'll need it for CCMC:

```bash
grep -A2 '"auth"' ~/.openclaw/openclaw.json | grep '"token"'
```

## Step 2: Configure Trusted-Proxy Auth (Recommended)

Trusted-proxy auth lets CCMC connect through your reverse proxy without device pairing.

Edit `~/.openclaw/openclaw.json` and update the `gateway` section:

```json5
{
  "gateway": {
    "bind": "lan",
    "port": 18789,
    "trustedProxies": ["YOUR_NPM_IP"],
    "auth": {
      "mode": "trusted-proxy",
      "trustedProxy": {
        "userHeader": "x-forwarded-user"
      },
      "token": "YOUR_EXISTING_TOKEN"
    }
  }
}
```

Replace:
- `YOUR_NPM_IP` — your Nginx Proxy Manager IP address (e.g., `10.0.10.8`)
- `YOUR_EXISTING_TOKEN` — keep your existing gateway token for API access

If you also need local CLI access, add localhost to trustedProxies:
```json
"trustedProxies": ["YOUR_NPM_IP", "127.0.0.1", "::1", "YOUR_GATEWAY_IP"]
```

The gateway will reload automatically after saving the config file.

Verify with:
```bash
openclaw gateway status --deep
```

## Step 3: Configure Nginx Proxy Manager

### Create Proxy Host

| Setting | Value |
|---------|-------|
| **Domain Names** | `gateway.cleoclaw.com` (your chosen domain) |
| **Scheme** | `http` |
| **Forward Hostname / IP** | Your OpenClaw server IP (e.g., `10.0.10.21`) |
| **Forward Port** | `18789` |
| **Cache Assets** | OFF |
| **Block Common Exploits** | ON |
| **Websockets Support** | ON (required for RPC) |

### SSL Tab

| Setting | Value |
|---------|-------|
| **SSL Certificate** | Request new Let's Encrypt certificate |
| **Force SSL** | ON |
| **HTTP/2 Support** | ON |
| **HSTS Enabled** | ON |
| **HSTS Subdomains** | ON |

### Advanced Tab — Custom Nginx Configuration

```nginx
proxy_set_header X-Forwarded-User ccmc@mission-control;
proxy_read_timeout 86400s;
proxy_buffering off;
```

- `X-Forwarded-User` identifies CCMC to the gateway's trusted-proxy auth system
- `proxy_read_timeout` keeps SSE streams alive for real-time board chat and task updates
- `proxy_buffering off` prevents Nginx from buffering SSE/chunked responses (fixes `ERR_INCOMPLETE_CHUNKED_ENCODING`)

### Required: Add CCMC Origin to Gateway Allowed Origins

On your OpenClaw server, add your CCMC and gateway domains to the allowed origins:

```bash
# Edit ~/.openclaw/openclaw.json, update gateway.controlUi.allowedOrigins:
```

```json
{
  "gateway": {
    "controlUi": {
      "allowedOrigins": [
        "https://gateway.cleoclaw.com",
        "http://YOUR_GATEWAY_IP:18789",
        "http://localhost:18789"
      ]
    }
  }
}
```

## Step 4: Create Gateway in CCMC

1. Open CCMC → **Gateways** → **Create Gateway**
2. Enter:
   - **Gateway name**: A friendly name (e.g., "Production Gateway")
   - **Gateway address**: Your domain (e.g., `gateway.cleoclaw.com`) or IP:port
   - **Gateway token**: The auth token from Step 1
3. Click **Create gateway**

### What happens automatically:
- CCMC validates connectivity via HTTP health check
- Creates an MC Gateway Agent on your OpenClaw instance
- Creates a default "General" board
- Routes you to the board with a welcome modal

### If device pairing is required:
If the gateway isn't configured with trusted-proxy auth, a pairing approval modal will appear:
1. On your gateway server, run: `openclaw devices list`
2. Approve the pending request: `openclaw devices approve <request-id>`
3. The modal auto-detects approval and completes setup

Device pairing is a one-time step — the device token persists across restarts.

## Troubleshooting

### "Gateway is not reachable"
- Verify the gateway is running: `openclaw gateway status --deep`
- Check firewall allows port 18789 from your NPM IP
- If using FQDN, verify DNS resolves correctly

### "Timed out during opening handshake"
- Ensure NPM has **Websockets Support** enabled
- Check that `trustedProxies` includes your NPM IP
- Verify the gateway port matches (default: 18789)

### "Gateway must have a gateway main agent"
- This means the gateway onboarding didn't complete fully
- Try deleting and re-creating the gateway in CCMC

### Agent shows "offline"
- The agent is created but hasn't sent a heartbeat yet
- Check the gateway logs: `tail -f /tmp/openclaw/openclaw-*.log`

## Architecture Reference

```
Browser → CCMC Frontend (Next.js :3010)
              ↓ API proxy
         CCMC Backend (FastAPI :8010)
              ↓ HTTP + WebSocket RPC
         NPM (Nginx :443)
              ↓ proxy_pass + x-forwarded-user header
         OpenClaw Gateway (:18789)
```

All CCMC-to-gateway traffic flows through NPM when using an FQDN address.
Direct IP:port connections bypass NPM (useful for LAN-only setups).
