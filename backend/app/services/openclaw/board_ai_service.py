"""AI-assisted board creation service using gateway chat completions.

All LLM work is delegated to the connected gateway via POST /v1/chat/completions.
CCMC has no AI runtime of its own — this service is a thin coordination layer.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.schemas.board_ai import BoardCreationDraft
from app.services.openclaw.gateway_sdk.errors import GatewayError
from app.services.openclaw.gateway_sdk.manager import gateway_manager

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a board creation assistant for a project management system.
Your job is to parse a natural language description of a project board into structured JSON.

Respond ONLY with a JSON object matching this schema (no explanation, no markdown prose):

{
  "name": "<short board name, 2-6 words>",
  "description": "<one-sentence summary of the board's purpose>",
  "board_type": "<\"goal\" if this is an outcome-oriented project, else \"general\">",
  "objective": "<clear statement of the desired outcome — required for goal boards>",
  "success_metrics": {
    "<metric_name>": "<measurable target>"
  },
  "target_date": "<ISO 8601 date string if a deadline is mentioned, else null>",
  "suggested_tags": ["<tag1>", "<tag2>"],
  "lead_agent_name": "<a descriptive agent name appropriate for this board, or null>",
  "lead_agent_identity": {
    "role": "<agent role title>",
    "communication_style": "<e.g. direct, analytical, collaborative>",
    "emoji": "<a single representative emoji code like :rocket:>"
  }
}

Rules:
- Always produce valid JSON.
- If a field cannot be determined from the description, use null.
- success_metrics should contain 2-4 specific, measurable criteria.
- suggested_tags should be lowercase, hyphenated slugs (e.g. "frontend", "api-design").
- Do not include any text outside the JSON object.
"""

_REFINE_SYSTEM_PROMPT = """\
You are a board creation assistant for a project management system.
You are given an existing board draft in JSON form and user feedback requesting changes.
Apply the feedback and respond ONLY with the updated JSON object — no explanation, no markdown prose.

The JSON schema is:

{
  "name": "<short board name, 2-6 words>",
  "description": "<one-sentence summary>",
  "board_type": "<\"goal\" or \"general\">",
  "objective": "<clear outcome statement>",
  "success_metrics": { "<metric_name>": "<measurable target>" },
  "target_date": "<ISO 8601 date or null>",
  "suggested_tags": ["<tag>"],
  "lead_agent_name": "<name or null>",
  "lead_agent_identity": {
    "role": "<role title>",
    "communication_style": "<style>",
    "emoji": "<emoji code>"
  }
}

Rules:
- Only modify fields that the feedback explicitly asks to change.
- Preserve all other fields from the existing draft.
- Always produce valid JSON.
- Do not include any text outside the JSON object.
"""


def _extract_json_from_response(text: str) -> dict[str, Any]:
    """Parse JSON from a gateway response, handling fenced code blocks."""
    text = text.strip()

    # 1. Try direct parse first (ideal case — model followed instructions)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Extract from fenced code block: ```json ... ``` or ``` ... ```
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Grab the first {...} block from the raw text
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("board_ai.extract_json.failed raw_response_len=%d", len(text))
    return {}


class BoardAIService:
    """AI-assisted board creation using gateway chat completions.

    All LLM calls are forwarded to the connected OpenClaw gateway.  The gateway
    handles provider authentication, model routing, and rate limiting — this
    service only assembles prompts and interprets responses.
    """

    async def generate_board_draft(
        self,
        user_description: str,
        *,
        gateway_id: UUID,
    ) -> BoardCreationDraft:
        """Parse a natural language description into structured board fields.

        Sends a single system + user message pair to the gateway's
        POST /v1/chat/completions endpoint and deserialises the JSON response
        into a ``BoardCreationDraft``.

        Args:
            user_description: Free-form text describing the board the user wants.
            gateway_id: ID of the registered gateway to route the request through.

        Returns:
            A ``BoardCreationDraft`` with fields populated from the AI response.
            Fields the AI could not determine will be ``None``.

        Raises:
            ValueError: If the gateway is not registered.
            GatewayError: On transport, authentication, or upstream HTTP errors.
        """
        client = gateway_manager.require(gateway_id)

        logger.info(
            "board_ai.generate.start gateway_id=%s description_len=%d",
            gateway_id,
            len(user_description),
        )

        raw = await client.http.chat_completions_text(
            _SYSTEM_PROMPT,
            user_description,
        )

        logger.debug(
            "board_ai.generate.raw_response gateway_id=%s response_len=%d",
            gateway_id,
            len(raw),
        )

        data = _extract_json_from_response(raw)

        try:
            draft = BoardCreationDraft.model_validate(data)
        except Exception:
            logger.warning(
                "board_ai.generate.validation_failed gateway_id=%s data_keys=%s",
                gateway_id,
                list(data.keys()),
                exc_info=True,
            )
            draft = BoardCreationDraft()

        logger.info(
            "board_ai.generate.success gateway_id=%s name=%r board_type=%s",
            gateway_id,
            draft.name,
            draft.board_type,
        )
        return draft

    async def refine_board_draft(
        self,
        current_draft: BoardCreationDraft,
        user_feedback: str,
        *,
        gateway_id: UUID,
    ) -> BoardCreationDraft:
        """Refine an existing board draft based on user feedback.

        Serialises the current draft as JSON, embeds it alongside the user
        feedback in a single prompt turn, and parses the updated draft from
        the gateway response.

        Args:
            current_draft: The draft to be refined.
            user_feedback: Natural language instructions describing the changes.
            gateway_id: ID of the registered gateway to route the request through.

        Returns:
            An updated ``BoardCreationDraft`` reflecting the requested changes.

        Raises:
            ValueError: If the gateway is not registered.
            GatewayError: On transport, authentication, or upstream HTTP errors.
        """
        client = gateway_manager.require(gateway_id)

        draft_json = current_draft.model_dump_json(indent=2)
        user_message = (
            f"Current draft:\n```json\n{draft_json}\n```\n\n"
            f"User feedback: {user_feedback}"
        )

        logger.info(
            "board_ai.refine.start gateway_id=%s feedback_len=%d",
            gateway_id,
            len(user_feedback),
        )

        raw = await client.http.chat_completions_text(
            _REFINE_SYSTEM_PROMPT,
            user_message,
        )

        logger.debug(
            "board_ai.refine.raw_response gateway_id=%s response_len=%d",
            gateway_id,
            len(raw),
        )

        data = _extract_json_from_response(raw)

        try:
            refined = BoardCreationDraft.model_validate(data)
        except Exception:
            logger.warning(
                "board_ai.refine.validation_failed gateway_id=%s data_keys=%s — returning original",
                gateway_id,
                list(data.keys()),
                exc_info=True,
            )
            return current_draft

        logger.info(
            "board_ai.refine.success gateway_id=%s name=%r board_type=%s",
            gateway_id,
            refined.name,
            refined.board_type,
        )
        return refined


# Module-level singleton — import and use directly.
board_ai_service = BoardAIService()
