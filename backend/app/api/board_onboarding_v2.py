"""Board onboarding v2 API — MC-owned wizard form + SDK AI refinement.

Two-phase design:
- Phase 1: all structured data is collected by the frontend as plain form fields.
  No LLM, no agent chat, no parsing required.
- Phase 2: POST /refine sends the wizard data to the gateway via a single
  /v1/chat/completions call and returns structured AI refinements.
- POST /complete: combines both phases to provision the board and lead agent.

The existing v1 onboarding routes are left untouched for backward compatibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    get_board_for_user_write,
    require_user_auth,
)
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import get_session
from app.schemas.board_onboarding_v2 import (
    OnboardingAIRefinement,
    OnboardingCompleteRequest,
    OnboardingRefineResponse,
    OnboardingWizardData,
)
from app.schemas.boards import BoardRead
from app.services.openclaw.gateway_dispatch import GatewayDispatchService
from app.services.openclaw.onboarding_v2_service import OnboardingV2Service
from app.services.openclaw.provisioning_db import (
    LeadAgentOptions,
    LeadAgentRequest,
    OpenClawProvisioningService,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.auth import AuthContext
    from app.models.boards import Board

router = APIRouter(
    prefix="/boards/{board_id}/onboarding/v2",
    tags=["board-onboarding-v2"],
)
logger = get_logger(__name__)

BOARD_USER_WRITE_DEP = Depends(get_board_for_user_write)
SESSION_DEP = Depends(get_session)
USER_AUTH_DEP = Depends(require_user_auth)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_user_profile_from_wizard(
    auth: AuthContext,
    wizard: OnboardingWizardData,
) -> bool:
    """Apply user-profile fields from wizard data onto the authenticated user model.

    Returns True when at least one field was changed.
    """
    if auth.user is None:
        return False

    changed = False
    if wizard.preferred_name is not None:
        stripped = wizard.preferred_name.strip()
        if stripped:
            auth.user.preferred_name = stripped
            changed = True
    if wizard.pronouns is not None:
        stripped = wizard.pronouns.strip()
        if stripped:
            auth.user.pronouns = stripped
            changed = True
    if wizard.timezone is not None:
        stripped = wizard.timezone.strip()
        if stripped:
            auth.user.timezone = stripped
            changed = True
    return changed


def _lead_agent_options_from_v2(
    wizard: OnboardingWizardData,
    refinement: OnboardingAIRefinement,
) -> LeadAgentOptions:
    """Build LeadAgentOptions from wizard + refinement data for provisioning."""
    # Start with the AI-generated identity profile (role, communication_style, emoji).
    identity_profile: dict[str, str] = {}
    if refinement.identity_profile:
        identity_profile.update(
            {k: v.strip() for k, v in refinement.identity_profile.items() if v.strip()}
        )

    # Overlay the explicit wizard preference fields so they are always present
    # in the agent's identity profile regardless of what the LLM generated.
    identity_profile["autonomy_level"] = wizard.autonomy_level
    identity_profile["verbosity"] = wizard.verbosity
    identity_profile["output_format"] = wizard.output_format
    identity_profile["update_cadence"] = wizard.update_cadence
    if wizard.custom_instructions:
        identity_profile["custom_instructions"] = wizard.custom_instructions.strip()

    return LeadAgentOptions(
        agent_name=wizard.agent_name,
        identity_profile=identity_profile or None,
        action="provision",
    )


def _require_approval_for_done(autonomy_level: str) -> bool:
    """Return False (disable done-approval gate) only for fully autonomous mode."""
    return autonomy_level != "autonomous"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/refine", response_model=OnboardingRefineResponse)
async def refine_onboarding(
    payload: OnboardingWizardData,
    board: Board = BOARD_USER_WRITE_DEP,
    session: AsyncSession = SESSION_DEP,
) -> OnboardingRefineResponse:
    """Phase 2: send wizard data to the gateway LLM for AI refinement.

    Accepts the structured wizard form data collected by the frontend and sends
    it to the gateway via a single POST /v1/chat/completions call.  Returns a
    refined board objective, description, success metrics, and a complete
    SOUL.md template for the lead agent.

    This endpoint has no side-effects — it does not persist any data.
    """
    gateway, _config = await GatewayDispatchService(session).require_gateway_config_for_board(
        board
    )

    logger.info(
        "onboarding_v2.refine board_id=%s gateway_id=%s agent_name=%s",
        board.id,
        gateway.id,
        payload.agent_name,
    )

    refinement = await OnboardingV2Service().generate_refinement(
        payload,
        gateway_id=gateway.id,
    )
    return OnboardingRefineResponse(refinement=refinement)


@router.post("/complete", response_model=BoardRead)
async def complete_onboarding(
    payload: OnboardingCompleteRequest,
    board: Board = BOARD_USER_WRITE_DEP,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = USER_AUTH_DEP,
) -> Board:
    """Phase 1+2 combined: provision the board and lead agent.

    Accepts the combined wizard + refinement data, applies user-profile fields,
    sets board goal metadata, and provisions the lead agent.

    This endpoint has durable side-effects:
    - Updates the board's objective, description, board_type, success_metrics,
      and goal_confirmed flag.
    - Creates the lead agent record and provisions it on the gateway.
    - Optionally updates the user's preferred_name, pronouns, and timezone.
    """
    wizard = payload.wizard
    refinement = payload.refinement

    logger.info(
        "onboarding_v2.complete board_id=%s agent_name=%s autonomy=%s",
        board.id,
        wizard.agent_name,
        wizard.autonomy_level,
    )

    # Apply board goal fields from refinement.
    board.board_type = wizard.board_type
    board.objective = refinement.objective
    board.description = refinement.description

    if wizard.board_type == "goal":
        if not refinement.objective:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="objective is required for goal boards",
            )
        board.success_metrics = refinement.success_metrics

    board.goal_confirmed = True
    board.goal_source = "wizard_v2"
    board.require_approval_for_done = _require_approval_for_done(wizard.autonomy_level)
    board.updated_at = utcnow()

    # Apply user profile updates when present.
    if _apply_user_profile_from_wizard(auth, wizard) and auth.user is not None:
        session.add(auth.user)

    # Resolve the gateway for provisioning.
    gateway, config = await GatewayDispatchService(session).require_gateway_config_for_board(board)

    session.add(board)
    await session.commit()
    await session.refresh(board)

    # Provision the lead agent with the wizard + refinement identity profile.
    lead_options = _lead_agent_options_from_v2(wizard, refinement)
    await OpenClawProvisioningService(session).ensure_board_lead_agent(
        request=LeadAgentRequest(
            board=board,
            gateway=gateway,
            config=config,
            user=auth.user,
            options=lead_options,
        ),
    )

    logger.info(
        "onboarding_v2.complete.success board_id=%s agent_name=%s",
        board.id,
        wizard.agent_name,
    )
    return board
