"""Real OpenClaw agent provisioning for CCMC.

Creates discrete agents on OpenClaw with their own workspace, auth profiles,
session store, and workspace templates. Each agent is a fully isolated entity
that can run concurrently.

CRITICAL: CleoClaw agents MUST be discrete OpenClaw agents. The user's "main"
OpenClaw agent is NEVER touched, modified, or routed through.

Architecture:
    1. agents.create RPC  → registers agent in OpenClaw config
    2. config.patch RPC   → sets full tools profile + sandbox off
    3. Local filesystem cp → copies auth-profiles.json from main agent
    4. agents.files.set    → deploys CCMC workspace templates
    5. exec-approvals.json → configures per-agent exec policy

Since CCMC and OpenClaw run on the same host, step 3 is a direct file copy —
no RPC, SSH, or exec tool needed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.services.openclaw.gateway_sdk.client import GatewayClient
from app.services.openclaw.gateway_sdk.errors import GatewayRPCError

logger = get_logger(__name__)

# Default OpenClaw state directory.
OPENCLAW_STATE_DIR = Path.home() / ".openclaw"


def _resolve_state_dir() -> Path:
    """Resolve the OpenClaw state directory (respects $OPENCLAW_STATE_DIR)."""
    import os

    env = os.environ.get("OPENCLAW_STATE_DIR", "").strip()
    return Path(env) if env else OPENCLAW_STATE_DIR


def _agent_dir(agent_id: str) -> Path:
    """Return the agentDir path for a given agent ID."""
    return _resolve_state_dir() / "agents" / agent_id / "agent"


def _main_auth_profiles_path() -> Path:
    """Path to the main agent's auth-profiles.json (READ-ONLY source)."""
    return _agent_dir("main") / "auth-profiles.json"


def copy_auth_from_main(agent_id: str) -> bool:
    """Copy auth-profiles.json from the main agent to a new agent.

    This is a READ-ONLY operation on the main agent — we only copy FROM it,
    never write TO it. The copy gives the new agent its own independent
    auth-profiles.json file.

    Returns True if the copy succeeded, False if the source doesn't exist
    or the copy failed.
    """
    src = _main_auth_profiles_path()
    if not src.exists():
        logger.warning(
            "agent_provisioner.copy_auth.source_missing agent=%s src=%s",
            agent_id,
            src,
        )
        return False

    dst_dir = _agent_dir(agent_id)
    dst = dst_dir / "auth-profiles.json"

    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        # Secure the file (readable only by owner).
        dst.chmod(0o600)
        logger.info(
            "agent_provisioner.copy_auth.success agent=%s dst=%s",
            agent_id,
            dst,
        )
        return True
    except Exception as exc:
        logger.error(
            "agent_provisioner.copy_auth.failed agent=%s error=%s",
            agent_id,
            exc,
        )
        return False


def update_exec_approvals(agent_id: str, security: str = "full", ask: str = "off") -> bool:
    """Add or update per-agent exec approval settings in exec-approvals.json.

    Sets the agent's exec policy so CCMC agents can run commands
    (particularly curl for API callbacks) without manual approval.
    """
    approvals_path = _resolve_state_dir() / "exec-approvals.json"

    try:
        if approvals_path.exists():
            data = json.loads(approvals_path.read_text(encoding="utf-8"))
        else:
            data = {"version": 1, "defaults": {}, "agents": {}}

        if "agents" not in data:
            data["agents"] = {}

        data["agents"][agent_id] = {
            "security": security,
            "ask": ask,
            "askFallback": security,
            "autoAllowSkills": True,
        }

        approvals_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("agent_provisioner.exec_approvals.updated agent=%s security=%s", agent_id, security)
        return True
    except Exception as exc:
        logger.error("agent_provisioner.exec_approvals.failed agent=%s error=%s", agent_id, exc)
        return False


async def _configure_agent_tools(client: GatewayClient, agent_id: str) -> bool:
    """Set full tools profile on a new agent via config.set.

    Gives the agent unrestricted tool access (profile: full, sandbox: off)
    so it can perform all necessary operations.
    """
    try:
        # Use config.set for individual path-based updates (simpler, no merge-patch).
        await client.rpc.config_set(f"agents.list.{agent_id}.tools", {"profile": "full"})
        await client.rpc.config_set(f"agents.list.{agent_id}.sandbox", {"mode": "off"})
        logger.info("agent_provisioner.tools_config.success agent=%s", agent_id)
        return True
    except GatewayRPCError as exc:
        # config.set may not support dot-path into agent list.
        # Fall back to raw RPC call without response validation.
        logger.warning(
            "agent_provisioner.tools_config.set_failed agent=%s, trying patch: %s",
            agent_id,
            exc,
        )
        try:
            import json as _json

            current_raw = await client.rpc._call("config.get")
            if not isinstance(current_raw, dict):
                return False

            base_hash = current_raw.get("hash")
            agents_list = current_raw.get("config", {}).get("agents", {}).get("list", [])

            for entry in agents_list:
                if entry.get("id") == agent_id:
                    entry["tools"] = {"profile": "full"}
                    entry["sandbox"] = {"mode": "off"}
                    break

            patch = {"agents": {"list": agents_list}}
            params: dict = {"raw": _json.dumps(patch)}
            if base_hash:
                params["baseHash"] = base_hash

            await client.rpc._call("config.patch", params)
            logger.info("agent_provisioner.tools_config.patch_success agent=%s", agent_id)
            return True
        except Exception as inner_exc:
            logger.error(
                "agent_provisioner.tools_config.patch_failed agent=%s error=%s",
                agent_id,
                inner_exc,
            )
            return False
    except Exception as exc:
        logger.error("agent_provisioner.tools_config.failed agent=%s error=%s", agent_id, exc)
        return False


async def provision_agent(
    *,
    client: GatewayClient,
    agent_name: str,
    workspace_path: str | None = None,
    deploy_templates: bool = True,
    template_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Provision a complete, real agent on OpenClaw.

    CRITICAL: This creates a DISCRETE agent — never touches the "main" agent.

    Steps:
        1. Create agent via agents.create RPC
        2. Configure full tools profile via config.patch RPC
        3. Copy auth-profiles.json from main agent (local filesystem, READ-ONLY)
        4. Configure exec approvals for the agent
        5. Deploy CCMC workspace templates

    Args:
        client: GatewayClient connected to the gateway.
        agent_name: Display name for the agent.
        workspace_path: Workspace directory path (default: auto-derived).
        deploy_templates: Whether to deploy CCMC workspace templates.
        template_context: Variables for template rendering.

    Returns:
        Dict with provisioning results:
        ``{"agent_id": str, "auth_copied": bool, "templates": dict,
          "exec_approvals": bool, "tools_configured": bool}``
    """
    import re

    # Derive agent ID from name (OpenClaw normalizes to lowercase alphanumeric + hyphens).
    slug = re.sub(r"[^a-z0-9]+", "-", agent_name.lower()).strip("-")
    agent_id = slug

    if not workspace_path:
        workspace_path = f"~/.openclaw/workspace-{slug}"

    result: dict[str, Any] = {"agent_id": agent_id, "name": agent_name}

    # Step 1: Create agent on OpenClaw via RPC.
    try:
        existing = await client.rpc.agents_list()
        already_exists = any(a.id == agent_id for a in existing.agents)

        if already_exists:
            logger.info("agent_provisioner.create.exists agent=%s", agent_id)
            result["created"] = "exists"
        else:
            await client.rpc.agents_create(
                name=agent_name,
                workspace=workspace_path,
            )
            result["created"] = True
            logger.info("agent_provisioner.create.success agent=%s", agent_id)
    except GatewayRPCError as exc:
        if "already exists" in str(exc).lower():
            result["created"] = "exists"
        else:
            result["created"] = False
            result["create_error"] = str(exc)
            logger.error("agent_provisioner.create.failed agent=%s error=%s", agent_id, exc)
            return result

    # Step 2: Configure full tools profile via config.patch.
    result["tools_configured"] = await _configure_agent_tools(client, agent_id)

    # Step 3: Copy auth from main agent (local filesystem, READ-ONLY on main).
    result["auth_copied"] = copy_auth_from_main(agent_id)

    # Step 4: Configure exec approvals.
    result["exec_approvals"] = update_exec_approvals(agent_id)

    # Step 5: Deploy workspace templates.
    if deploy_templates:
        try:
            from app.services.openclaw.workspace_templates import (
                deploy_workspace_files,
                render_workspace_files,
            )

            ctx = template_context or {}
            files = render_workspace_files(
                agent_name=ctx.get("agent_name", agent_name),
                agent_role=ctx.get("agent_role", "Worker Agent"),
                board_name=ctx.get("board_name", "General"),
                gateway_name=ctx.get("gateway_name", ""),
                user_name=ctx.get("user_name", ""),
                org_name=ctx.get("org_name", ""),
                base_url=ctx.get("base_url", ""),
                board_id=ctx.get("board_id", ""),
            )
            deploy_result = await deploy_workspace_files(
                rpc_client=client.rpc,
                agent_id=agent_id,
                files=files,
                force=True,
            )
            result["templates"] = deploy_result
        except Exception as exc:
            result["templates"] = {"error": str(exc)}
            logger.warning("agent_provisioner.templates.failed agent=%s error=%s", agent_id, exc)

    return result
