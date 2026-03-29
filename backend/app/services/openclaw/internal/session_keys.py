"""Deterministic session-key helpers for OpenClaw agents.

Session keys are part of Mission Control's contract with the OpenClaw gateway.
Centralize the string formats here to avoid drift across provisioning, DB workflows,
and API-facing services.

Session key format: ``agent:<agentId>:<mainKey>``
The ``agentId`` determines which OpenClaw agent handles the request.
Each CleoClaw agent is a REAL, discrete OpenClaw agent — never route through "main".
"""

from __future__ import annotations

from uuid import UUID

from app.services.openclaw.shared import GatewayAgentIdentity


def gateway_main_session_key(gateway_id: UUID) -> str:
    """Return the deterministic session key for a gateway-main agent."""
    return GatewayAgentIdentity.session_key_for_id(gateway_id)


def agent_session_key(openclaw_agent_id: str) -> str:
    """Return the session key for a real OpenClaw agent.

    Each CleoClaw agent maps 1:1 to a discrete OpenClaw agent.
    Format: ``agent:{openclaw_agent_id}:main``

    NEVER route through the OpenClaw "main" agent — it is the user's
    personal agent and must remain untouched by CleoClaw.
    """
    return f"agent:{openclaw_agent_id}:main"


def board_lead_session_key(openclaw_agent_id: str) -> str:
    """Return the session key for a board lead agent.

    Routes to the board lead's own discrete OpenClaw agent.
    Format: ``agent:{openclaw_agent_id}:main``
    """
    return agent_session_key(openclaw_agent_id)


def board_agent_session_key(openclaw_agent_id: str) -> str:
    """Return the session key for a non-lead board agent.

    Routes to the agent's own discrete OpenClaw agent.
    Format: ``agent:{openclaw_agent_id}:main``
    """
    return agent_session_key(openclaw_agent_id)


def board_scoped_session_key(
    *,
    openclaw_agent_id: str,
    is_board_lead: bool,
) -> str:
    """Return the deterministic session key for a board-scoped agent."""
    if is_board_lead:
        return board_lead_session_key(openclaw_agent_id)
    return board_agent_session_key(openclaw_agent_id)
