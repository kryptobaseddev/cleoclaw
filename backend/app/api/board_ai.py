"""API endpoints for AI-assisted board creation via the connected gateway."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_org_member
from app.core.logging import get_logger
from app.schemas.board_ai import BoardAIGenerateRequest, BoardAIRefineRequest, BoardCreationDraft
from app.services.openclaw.board_ai_service import board_ai_service
from app.services.openclaw.gateway_sdk.errors import GatewayAuthError, GatewayConnectionError, GatewayError, GatewayTimeoutError
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/boards/ai", tags=["board-ai"])
logger = get_logger(__name__)

ORG_MEMBER_DEP = Depends(require_org_member)

_ERR_GATEWAY_NOT_REGISTERED = (
    "Gateway is not registered. Ensure the gateway is connected before using AI board creation."
)
_ERR_GATEWAY_UNREACHABLE = (
    "Could not reach the gateway. Check that the gateway is running and reachable."
)
_ERR_GATEWAY_AUTH = (
    "Gateway authentication failed. Verify the gateway token is valid."
)
_ERR_GATEWAY_TIMEOUT = (
    "The gateway took too long to respond. Please try again."
)
_ERR_GATEWAY_UPSTREAM = (
    "The gateway returned an error while generating the board draft. Please try again."
)


def _gateway_id_from_str(raw: str) -> UUID:
    """Parse a gateway ID string into a UUID or raise HTTP 422."""
    try:
        return UUID(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="gateway_id is not a valid UUID",
        )


def _handle_gateway_error(exc: GatewayError) -> None:
    """Translate GatewayError subclasses into appropriate HTTP exceptions."""
    if isinstance(exc, GatewayAuthError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_ERR_GATEWAY_AUTH,
        ) from exc
    if isinstance(exc, GatewayTimeoutError):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=_ERR_GATEWAY_TIMEOUT,
        ) from exc
    if isinstance(exc, GatewayConnectionError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_ERR_GATEWAY_UNREACHABLE,
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=_ERR_GATEWAY_UPSTREAM,
    ) from exc


@router.post("/generate", response_model=BoardCreationDraft)
async def generate_board_draft(
    payload: BoardAIGenerateRequest,
    _ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> BoardCreationDraft:
    """Generate a structured board draft from a natural language description.

    Forwards the user description to the connected gateway's chat completions
    endpoint and returns a structured draft suitable for pre-filling the board
    creation form.
    """
    gateway_id = _gateway_id_from_str(payload.gateway_id)

    try:
        return await board_ai_service.generate_board_draft(
            payload.description,
            gateway_id=gateway_id,
        )
    except ValueError as exc:
        # gateway_manager.require raises ValueError when gateway not registered
        logger.warning(
            "board_ai.generate.gateway_not_registered gateway_id=%s",
            gateway_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_ERR_GATEWAY_NOT_REGISTERED,
        ) from exc
    except GatewayError as exc:
        logger.warning(
            "board_ai.generate.gateway_error gateway_id=%s error=%s",
            gateway_id,
            exc,
        )
        _handle_gateway_error(exc)


@router.post("/refine", response_model=BoardCreationDraft)
async def refine_board_draft(
    payload: BoardAIRefineRequest,
    _ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> BoardCreationDraft:
    """Refine an existing board draft based on natural language feedback.

    Sends the current draft and user feedback to the connected gateway and
    returns an updated draft with the requested changes applied.
    """
    gateway_id = _gateway_id_from_str(payload.gateway_id)

    try:
        return await board_ai_service.refine_board_draft(
            payload.draft,
            payload.feedback,
            gateway_id=gateway_id,
        )
    except ValueError as exc:
        logger.warning(
            "board_ai.refine.gateway_not_registered gateway_id=%s",
            gateway_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_ERR_GATEWAY_NOT_REGISTERED,
        ) from exc
    except GatewayError as exc:
        logger.warning(
            "board_ai.refine.gateway_error gateway_id=%s error=%s",
            gateway_id,
            exc,
        )
        _handle_gateway_error(exc)
