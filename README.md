# CleoClaw Mission Control

CleoClaw is a self-hosted control plane for [OpenClaw](https://github.com/openclaw/openclaw) AI agent instances. It gives you a single web dashboard to connect gateways, manage agents, run board-based chat, and govern operations across your OpenClaw deployment.

<!-- TODO: Add dashboard screenshot -->
<!-- ![CleoClaw Dashboard](docs/screenshots/dashboard.png) -->

## What CleoClaw does

- **Gateway onboarding wizard** — Step-by-step connection to OpenClaw instances with automatic agent provisioning, proxy configuration guidance, and health verification
- **Board-based agent chat** — Real-time messaging with discrete OpenClaw agents through a board UI. Each agent has its own workspace and tools
- **Agent lifecycle management** — Create, provision, monitor, and manage agents with live status indicators. Agents are real OpenClaw agents, not proxied through the main agent
- **Approval governance** — Route sensitive actions through explicit approval workflows with audit trails
- **Multi-organization support** — Teams, organizations, and role-based access powered by Better Auth

<!-- TODO: Add board chat screenshot -->
<!-- ![Board Chat](docs/screenshots/board-chat.png) -->

## What makes CleoClaw different

- **Your main agent stays untouched.** CleoClaw creates its own discrete agents on OpenClaw with isolated workspaces, auth profiles, and sessions. Your personal main agent is never modified, routed through, or contaminated
- **Batteries-included auth.** Email/password authentication with admin roles and organization management out of the box via [Better Auth](https://www.better-auth.com/). No external auth service needed
- **Gateway-aware orchestration.** Built specifically for OpenClaw's multi-agent architecture with proper session key routing, agent provisioning, and workspace template deployment
- **Self-hosted and private.** Runs entirely on your infrastructure. No cloud dependencies, no telemetry, no external calls except to your own OpenClaw instances

## Platform overview

CleoClaw is designed as the day-to-day operations surface for OpenClaw. Instead of SSH-ing into your server and managing agents via CLI, you get a web UI that handles:

- **Work orchestration** — Organizations, boards, tasks, and tags in a structured workspace
- **Agent operations** — Create, inspect, and manage agent lifecycle from a unified control surface
- **Gateway management** — Connect and operate OpenClaw instances from local or remote environments
- **Activity visibility** — Timeline of system actions for debugging and accountability
- **API-first model** — Every UI action is backed by an API endpoint for automation

## Who it's for

- **Self-hosters** running OpenClaw on their own infrastructure who want a web UI instead of CLI-only management
- **Teams** that need shared visibility into agent operations with role-based access control
- **Operators** who want approval workflows and audit trails for agent actions
- **Developers** building on top of OpenClaw who want an API-accessible operations layer

## Use cases

- **Personal AI operations** — Manage your OpenClaw instance from a web dashboard instead of terminal
- **Multi-agent orchestration** — Run multiple board-specific agents simultaneously with isolated workspaces
- **Approval-gated execution** — Require human approval before agents take sensitive actions
- **Remote gateway management** — Connect to OpenClaw instances running on different servers or VMs

## Architecture

```
Browser --> NPM (TLS) --> Next.js (:3011) --> FastAPI (:8011) --> OpenClaw Gateway (:18789)
                                                   |
                                                   v
                                              PostgreSQL
```

| Layer | Stack |
|-------|-------|
| **Frontend** | Next.js 16, React 19, TanStack Query/Table, Radix UI, Tailwind CSS |
| **Backend** | Python 3.12+, FastAPI, SQLAlchemy/SQLModel, Alembic |
| **Database** | PostgreSQL 15+ |
| **Auth** | Better Auth (email/password, admin roles, organizations) |
| **Queue** | Redis + RQ (background task processing) |

## Quick start

### Option A: Docker (recommended)

```bash
git clone https://github.com/kryptobaseddev/cleoclaw.git
cd cleoclaw
cp .env.example .env
```

Edit `.env` to set your `LOCAL_AUTH_TOKEN` (50+ characters) and database credentials, then:

```bash
docker compose up -d --build
```

CleoClaw will be available at `http://localhost:3000` with the backend at `http://localhost:8000`.

To rebuild after pulling changes:

```bash
docker compose up -d --build --force-recreate
```

### Option B: Local development

#### Prerequisites

- Node.js 22+ and npm
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- PostgreSQL 15+ (running)
- Redis (for background tasks)
- An OpenClaw instance ([install guide](https://docs.openclaw.ai/install/npm))

#### 1. Configure

```bash
git clone https://github.com/kryptobaseddev/cleoclaw.git
cd cleoclaw
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Key settings in `backend/.env`:
```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/mission_control
AUTH_MODE=local
LOCAL_AUTH_TOKEN=your-secure-token-at-least-50-characters-long-change-this
```

Key settings in `frontend/.env`:
```bash
NEXT_PUBLIC_API_URL=http://localhost:8011
NEXT_PUBLIC_AUTH_MODE=better-auth
BETTER_AUTH_SECRET=your-secret-at-least-32-characters
```

#### 2. Backend

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8011
```

#### 3. Frontend

```bash
cd frontend
npm install
npm run build
npm run start -- --hostname 0.0.0.0 --port 3011
```

#### 4. Open CleoClaw

Navigate to `http://localhost:3011`, create an account, and connect your first gateway.

## Gateway onboarding

The gateway wizard walks you through connecting to an OpenClaw instance:

<!-- TODO: Add wizard screenshot -->
<!-- ![Gateway Wizard](docs/screenshots/gateway-wizard.png) -->

### Step 1: Connect
Enter your OpenClaw gateway address and token. CleoClaw verifies the connection is reachable.

- **Local deployment** (same machine): Use `http://127.0.0.1:18789`
- **Remote deployment**: Use `http://<server-ip>:18789` or your domain

### Step 2: Proxy configuration
If you're using a reverse proxy (Nginx Proxy Manager, Caddy, etc.), the wizard shows the configuration needed for SSE (Server-Sent Events) support:

**For the CleoClaw proxy host:**
```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
```

**For the OpenClaw gateway proxy host** (if exposed via domain):
```nginx
proxy_set_header X-Forwarded-User ccmc@mission-control;
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
```

### Step 3: Create
Name your gateway and CleoClaw handles the rest:
1. Registers the gateway connection
2. Creates a dedicated CleoClaw agent on OpenClaw (with full tools, its own workspace and auth)
3. Sets up a default "General" board with a board lead agent
4. Verifies the agent is alive and responding

### Device pairing
If device pairing is required, CleoClaw will prompt you to approve the pairing on the OpenClaw instance:
```bash
openclaw devices list
openclaw devices approve <request-id>
```

## Authentication

CleoClaw uses [Better Auth](https://www.better-auth.com/) for authentication. No external auth service is required — everything runs locally.

- **Email/password** registration and login
- **Admin roles** for organization management
- **Organization/team** support for multi-user deployments
- **Session management** via SQLite (frontend-side)

First user to register becomes the admin. Additional users can be invited through the organization settings.

## Key design principle

**CleoClaw never touches your main OpenClaw agent.** All CleoClaw operations use dedicated, discrete agents with their own workspaces, auth profiles, and session stores. Your personal OpenClaw agent — its workspace files, Telegram pairing, and configuration — remains completely untouched.

## Documentation

- [Getting started](./docs/getting-started/)
- [Gateway onboarding](./docs/getting-started/gateway-onboarding.md)
- [Deployment guides](./docs/deployment/)
- [API reference](./docs/reference/api.md)
- [Configuration](./docs/reference/configuration.md)

## Project status

CleoClaw is under active development. Core features (gateway onboarding, board chat, agent management) are functional. APIs and features may change between releases.

### Roadmap

- [ ] Real-time SSE streaming for agent responses (typing indicators)
- [ ] Agent health status via OpenClaw heartbeat integration
- [ ] Provisioning status check in gateway wizard
- [ ] One-click installer for common platforms
- [ ] Skill marketplace integration

## Contributing

Issues and pull requests are welcome at [github.com/kryptobaseddev/cleoclaw](https://github.com/kryptobaseddev/cleoclaw).

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development guidelines.

## License

MIT — see [LICENSE](./LICENSE).

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=kryptobaseddev/cleoclaw&type=date)](https://star-history.com/#kryptobaseddev/cleoclaw&Date)
