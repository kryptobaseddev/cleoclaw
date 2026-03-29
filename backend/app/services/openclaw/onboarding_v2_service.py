"""Board onboarding v2 service — SDK-driven AI refinement.

Phase 1 (wizard form data) arrives fully structured from the frontend.
Phase 2 is a single deterministic POST /v1/chat/completions call that:
  - generates a complete SOUL.md template for the lead agent
  - refines the board objective and description
  - proposes success metrics
  - sets the lead agent identity profile

No curl, no exec, no polling, no agent chat sessions.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from app.core.logging import get_logger
from app.schemas.board_onboarding_v2 import OnboardingAIRefinement, OnboardingWizardData
from app.services.openclaw.gateway_sdk.errors import GatewayError
from app.services.openclaw.gateway_sdk.manager import gateway_manager

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_AUTONOMY_DESCRIPTIONS: dict[str, str] = {
    "ask_first": (
        "always asks before taking action, confirms plans with the user before executing, "
        "and waits for explicit approval on significant decisions"
    ),
    "balanced": (
        "uses judgment to decide when to act vs. when to check in, proposes plans for "
        "larger tasks while handling small tasks independently"
    ),
    "autonomous": (
        "acts independently, executes plans without waiting for approval, and only "
        "escalates genuinely ambiguous or irreversible decisions"
    ),
}

_VERBOSITY_DESCRIPTIONS: dict[str, str] = {
    "concise": "brief and to the point — minimal prose, maximum signal",
    "balanced": "clear and thorough without being verbose — includes context when it matters",
    "detailed": "comprehensive — explains reasoning, surfaces alternatives, provides full context",
}

_OUTPUT_FORMAT_DESCRIPTIONS: dict[str, str] = {
    "bullets": "structured bullet points and lists",
    "mixed": "a mix of prose and bullets depending on the content",
    "narrative": "flowing prose sentences and paragraphs",
}

_CADENCE_DESCRIPTIONS: dict[str, str] = {
    "asap": "sends updates immediately as events happen",
    "hourly": "rolls up updates roughly every hour",
    "daily": "provides a daily summary",
    "weekly": "provides a weekly digest",
}


def _build_system_prompt() -> str:
    return (
        "You are an expert AI project lead onboarding assistant for Mission Control, "
        "a platform where AI agents collaborate with humans to achieve goals.\n\n"
        "Your job is to take structured onboarding wizard answers and produce:\n"
        "1. A refined board objective — a single clear, actionable sentence that "
        "precisely captures what success looks like.\n"
        "2. A board description — 2–4 sentences elaborating on the objective, "
        "the approach, and why it matters.\n"
        "3. Success metrics — a JSON object with 2–4 measurable criteria.  "
        "Each key is a short metric name and each value is the target/definition.\n"
        "4. A complete SOUL.md file — the lead agent's core identity document that "
        "shapes how it thinks, communicates, and operates.  The SOUL.md must be "
        "thorough and specific to the wizard answers provided.\n"
        "5. An identity_profile — a small JSON object with keys: "
        '"role", "communication_style", and "emoji".\n\n'
        "SOUL.md REQUIREMENTS:\n"
        "- Must be a complete, standalone Markdown file the agent can load at startup.\n"
        "- Include these sections (in order): # SOUL, ## Identity, ## Mission, "
        "## Working Style, ## Communication, ## Boundaries.\n"
        "- ## Identity: name, role, a 2–3 sentence character description that "
        "reflects the autonomy level and personality implied by the name.\n"
        "- ## Mission: the board goal restated as the agent's personal mission.  "
        "Include 2–4 concrete responsibilities.\n"
        "- ## Working Style: translate the wizard's autonomy/verbosity/output_format/"
        "update_cadence selections into specific behavioral rules the agent follows.\n"
        "- ## Communication: rules about tone, formatting, when to escalate, "
        "and how to present updates.  Reflect the verbosity and output_format choices.\n"
        "- ## Boundaries: 3–5 hard rules about what the agent will NOT do without "
        "explicit human approval (calibrated to the autonomy level).\n"
        "- If custom_instructions were provided, incorporate them naturally.\n"
        "- If user profile info (preferred_name, pronouns, timezone) is present, "
        "reference it in Working Style or Communication where appropriate.\n\n"
        "RESPONSE FORMAT:\n"
        "Respond with a single valid JSON object and nothing else.  "
        "Do NOT include markdown code fences.  The schema is:\n"
        "{\n"
        '  "objective": "<single sentence>",\n'
        '  "description": "<2-4 sentences>",\n'
        '  "success_metrics": {"<metric>": "<target>", ...},\n'
        '  "soul_template": "<full SOUL.md content as a single string with \\n newlines>",\n'
        '  "identity_profile": {\n'
        '    "role": "<short role label>",\n'
        '    "communication_style": "<brief descriptor>",\n'
        '    "emoji": "<:emoji_name:>"\n'
        "  }\n"
        "}\n\n"
        "Be specific, practical, and grounded in the wizard answers.  "
        "Avoid generic filler language."
    )


def _build_user_message(wizard: OnboardingWizardData) -> str:
    lines: list[str] = [
        "ONBOARDING WIZARD DATA",
        "",
        f"Board name: {wizard.board_name}",
        f"Board type: {wizard.board_type}",
        f"Board goal (user's own words): {wizard.board_goal}",
        "",
        "Lead agent configuration:",
        f"  Agent name: {wizard.agent_name}",
        f"  Autonomy level: {wizard.autonomy_level} "
        f"— {_AUTONOMY_DESCRIPTIONS.get(wizard.autonomy_level, wizard.autonomy_level)}",
        f"  Verbosity: {wizard.verbosity} "
        f"— {_VERBOSITY_DESCRIPTIONS.get(wizard.verbosity, wizard.verbosity)}",
        f"  Output format: {wizard.output_format} "
        f"— {_OUTPUT_FORMAT_DESCRIPTIONS.get(wizard.output_format, wizard.output_format)}",
        f"  Update cadence: {wizard.update_cadence} "
        f"— {_CADENCE_DESCRIPTIONS.get(wizard.update_cadence, wizard.update_cadence)}",
    ]

    if wizard.custom_instructions:
        lines.append(f"  Custom instructions: {wizard.custom_instructions}")

    lines.append("")
    lines.append("User profile:")
    if wizard.preferred_name:
        lines.append(f"  Preferred name: {wizard.preferred_name}")
    if wizard.pronouns:
        lines.append(f"  Pronouns: {wizard.pronouns}")
    if wizard.timezone:
        lines.append(f"  Timezone: {wizard.timezone}")
    if not any([wizard.preferred_name, wizard.pronouns, wizard.timezone]):
        lines.append("  (not provided)")

    lines.append("")
    lines.append(
        "Generate the JSON refinement object described in the system prompt.  "
        "Ensure the SOUL.md is complete, specific to this agent and board, and "
        "actionable — not a generic template."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def _extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from the model response.

    Handles responses that accidentally include markdown fences or preamble.
    """
    # Fast path: the whole string is valid JSON
    stripped = text.strip()
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    try:
        obj = json.loads(cleaned.strip())
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Last resort: find the outermost { ... } block
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(stripped[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    msg = "Gateway returned a response that could not be parsed as a JSON object"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class OnboardingV2Service:
    """SDK-driven AI refinement for the v2 onboarding wizard.

    Sends the Phase 1 wizard data to the gateway via /v1/chat/completions and
    returns a structured OnboardingAIRefinement.  No agent sessions, no exec,
    no curl callbacks — one HTTP call, one structured response.
    """

    async def generate_refinement(
        self,
        wizard_data: OnboardingWizardData,
        *,
        gateway_id: UUID,
    ) -> OnboardingAIRefinement:
        """Send collected wizard data to the gateway for AI refinement.

        Args:
            wizard_data: Phase 1 form data from the frontend wizard.
            gateway_id: The UUID of the gateway whose LLM will process the request.

        Returns:
            OnboardingAIRefinement with soul_template, objective, description,
            success_metrics, and identity_profile populated.

        Raises:
            HTTPException 502: When the gateway is unreachable or returns an error.
            HTTPException 422: When the gateway response cannot be parsed.
        """
        client = gateway_manager.get(gateway_id)
        if client is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"Gateway {gateway_id} is not registered.  "
                    "Ensure the gateway is configured and the application has started."
                ),
            )

        system_prompt = _build_system_prompt()
        user_message = _build_user_message(wizard_data)

        logger.info(
            "onboarding_v2.generate_refinement.start gateway_id=%s agent_name=%s",
            gateway_id,
            wizard_data.agent_name,
        )

        try:
            raw_text = await client.http.chat_completions_text(
                system_prompt,
                user_message,
            )
        except GatewayError as exc:
            logger.error(
                "onboarding_v2.generate_refinement.gateway_error gateway_id=%s error=%s",
                gateway_id,
                str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Gateway error during AI refinement: {exc}",
            ) from exc

        if not raw_text:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gateway returned an empty response for AI refinement",
            )

        logger.debug(
            "onboarding_v2.generate_refinement.raw_response gateway_id=%s length=%d",
            gateway_id,
            len(raw_text),
        )

        try:
            data = _extract_json_object(raw_text)
        except ValueError as exc:
            logger.error(
                "onboarding_v2.generate_refinement.parse_error gateway_id=%s raw=%s",
                gateway_id,
                raw_text[:500],
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"AI refinement response could not be parsed: {exc}",
            ) from exc

        # Validate and coerce the parsed data into the response schema.
        try:
            refinement = OnboardingAIRefinement.model_validate(data)
        except Exception as exc:
            logger.error(
                "onboarding_v2.generate_refinement.validation_error gateway_id=%s error=%s data=%s",
                gateway_id,
                str(exc),
                str(data)[:500],
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"AI refinement response failed schema validation: {exc}",
            ) from exc

        logger.info(
            "onboarding_v2.generate_refinement.success gateway_id=%s objective_len=%d soul_len=%d",
            gateway_id,
            len(refinement.objective),
            len(refinement.soul_template),
        )
        return refinement
