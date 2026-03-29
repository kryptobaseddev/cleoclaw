"""Workspace template management for CCMC agents on OpenClaw.

Handles rendering, deploying, and integrity checking of agent workspace files.

Templates use ``{{variable}}`` placeholders for dynamic values.

Protected content is wrapped in CCMC tag blocks::

    <!-- CCMC:START — DO NOT EDIT THIS BLOCK -->
    ...managed content...
    <!-- CCMC:END -->

Agents may freely edit content OUTSIDE these blocks.  Integrity checks only
verify the content within CCMC blocks, allowing agents to add their own
notes, context, and customizations without triggering a false alarm.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates" / "workspace"

CCMC_BLOCK_START = "<!-- CCMC:START — DO NOT EDIT THIS BLOCK -->"
CCMC_BLOCK_END = "<!-- CCMC:END -->"

_CCMC_BLOCK_RE = re.compile(
    r"<!-- CCMC:START[^>]*-->(.+?)<!-- CCMC:END -->",
    re.DOTALL,
)

# Files where the CCMC block is critical and must be verified.
PROTECTED_FILES = frozenset({"AGENTS.md", "SOUL.md", "TOOLS.md", "BOOTSTRAP.md"})

# Files that agents may customize — CCMC writes initial version, doesn't overwrite.
EDITABLE_FILES = frozenset({"USER.md", "IDENTITY.md", "HEARTBEAT.md", "MEMORY.md"})

ALL_WORKSPACE_FILES = PROTECTED_FILES | EDITABLE_FILES


def _render_template(template_content: str, context: dict[str, Any]) -> str:
    """Render a template string, replacing ``{{key}}`` placeholders."""
    result = template_content
    for key, value in context.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


def render_workspace_files(
    *,
    agent_name: str,
    agent_role: str = "Board Lead",
    board_name: str = "General",
    gateway_name: str = "",
    user_name: str = "",
    org_name: str = "",
    base_url: str = "",
    board_id: str = "",
) -> dict[str, str]:
    """Render all workspace templates with the given context."""
    context = {
        "agent_name": agent_name,
        "agent_role": agent_role,
        "board_name": board_name,
        "gateway_name": gateway_name,
        "user_name": user_name,
        "org_name": org_name,
        "base_url": base_url,
        "board_id": board_id,
    }

    files: dict[str, str] = {}
    for filename in ALL_WORKSPACE_FILES:
        template_path = TEMPLATES_DIR / filename
        if template_path.exists():
            raw = template_path.read_text(encoding="utf-8")
            files[filename] = _render_template(raw, context)
        else:
            logger.warning("workspace_templates.missing template=%s", filename)
    return files


# ---------------------------------------------------------------------------
# CCMC block helpers
# ---------------------------------------------------------------------------


def extract_ccmc_blocks(content: str) -> list[str]:
    """Extract all CCMC-protected block contents from a file."""
    return _CCMC_BLOCK_RE.findall(content)


def compute_block_checksum(content: str) -> str:
    """SHA-256 of only the CCMC-protected blocks (ignoring agent edits outside)."""
    blocks = extract_ccmc_blocks(content)
    combined = "\n".join(b.strip() for b in blocks)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def compute_checksum(content: str) -> str:
    """SHA-256 of the full file content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Integrity checking
# ---------------------------------------------------------------------------


def check_integrity(
    deployed_files: dict[str, str],
    *,
    agent_name: str,
    **render_kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """Check integrity of workspace files on an OpenClaw agent.

    For protected files: compares CCMC block content against expected templates.
    For editable files: checks existence only.

    Returns::

        {
            "AGENTS.md": {"status": "ok", "has_ccmc_blocks": True},
            "SOUL.md":   {"status": "modified", "has_ccmc_blocks": True},
            "USER.md":   {"status": "ok"},
        }

    Status values: ``ok``, ``modified``, ``missing``, ``blocks_removed``.
    """
    expected = render_workspace_files(agent_name=agent_name, **render_kwargs)
    results: dict[str, dict[str, Any]] = {}

    for filename in ALL_WORKSPACE_FILES:
        if filename not in deployed_files:
            results[filename] = {"status": "missing"}
            continue

        deployed = deployed_files[filename]

        if filename in PROTECTED_FILES:
            expected_content = expected.get(filename, "")
            expected_blocks = extract_ccmc_blocks(expected_content)
            deployed_blocks = extract_ccmc_blocks(deployed)

            if not deployed_blocks and expected_blocks:
                results[filename] = {"status": "blocks_removed", "has_ccmc_blocks": False}
            elif compute_block_checksum(expected_content) != compute_block_checksum(deployed):
                results[filename] = {"status": "modified", "has_ccmc_blocks": bool(deployed_blocks)}
            else:
                results[filename] = {"status": "ok", "has_ccmc_blocks": True}
        else:
            results[filename] = {"status": "ok"}

    return results


def repair_ccmc_blocks(
    deployed_content: str,
    expected_content: str,
) -> str:
    """Repair CCMC blocks in a deployed file without touching agent content.

    Replaces CCMC blocks in *deployed_content* with the blocks from
    *expected_content*, preserving everything the agent wrote outside the blocks.
    If blocks were completely removed, appends them at the end.
    """
    deployed_blocks = list(_CCMC_BLOCK_RE.finditer(deployed_content))
    expected_blocks = extract_ccmc_blocks(expected_content)

    if not expected_blocks:
        return deployed_content

    expected_full_blocks = list(_CCMC_BLOCK_RE.finditer(expected_content))

    if deployed_blocks:
        # Replace each deployed block with the corresponding expected block.
        result = deployed_content
        for i, match in enumerate(reversed(deployed_blocks)):
            if i < len(expected_full_blocks):
                expected_match = expected_full_blocks[len(expected_full_blocks) - 1 - i]
                result = result[: match.start()] + expected_match.group(0) + result[match.end() :]
        return result

    # Blocks were removed — append at the end.
    full_blocks = [m.group(0) for m in expected_full_blocks]
    return deployed_content.rstrip() + "\n\n" + "\n\n".join(full_blocks) + "\n"


# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------


async def deploy_workspace_files(
    *,
    rpc_client: Any,
    agent_id: str,
    files: dict[str, str],
    force: bool = False,
) -> dict[str, str]:
    """Deploy workspace files to an OpenClaw agent via RPC.

    For protected files: always writes (ensures CCMC blocks are present).
    For editable files: writes only if the file doesn't exist (unless *force*).
    """
    results: dict[str, str] = {}

    existing_files: set[str] = set()
    try:
        file_list = await rpc_client.agents_files_list(agent_id)
        existing_files = {f.name for f in (file_list.files if hasattr(file_list, "files") else [])}
    except Exception:
        pass

    for filename, content in files.items():
        if not force and filename in EDITABLE_FILES and filename in existing_files:
            results[filename] = "skipped"
            continue

        try:
            await rpc_client.agents_files_set(agent_id, filename, content)
            results[filename] = "written"
        except Exception as exc:
            logger.warning(
                "workspace_templates.deploy_failed file=%s agent=%s error=%s",
                filename, agent_id, exc,
            )
            results[filename] = f"error: {exc}"

    return results


async def health_check(
    *,
    rpc_client: Any,
    agent_id: str,
    agent_name: str,
    auto_repair: bool = False,
    **render_kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """Run a full health check on workspace files.

    Reads all files from the agent, checks CCMC block integrity, and
    optionally repairs modified/missing blocks.
    """
    # Read deployed files.
    deployed: dict[str, str] = {}
    for filename in ALL_WORKSPACE_FILES:
        try:
            result = await rpc_client.agents_files_get(agent_id, filename)
            deployed[filename] = result.content if hasattr(result, "content") else str(result)
        except Exception:
            pass

    results = check_integrity(deployed, agent_name=agent_name, **render_kwargs)

    if auto_repair:
        expected = render_workspace_files(agent_name=agent_name, **render_kwargs)
        for filename, info in results.items():
            if info["status"] in ("modified", "blocks_removed", "missing"):
                expected_content = expected.get(filename, "")
                if not expected_content:
                    continue
                if info["status"] == "missing":
                    repaired = expected_content
                else:
                    repaired = repair_ccmc_blocks(deployed.get(filename, ""), expected_content)
                try:
                    await rpc_client.agents_files_set(agent_id, filename, repaired)
                    results[filename]["repaired"] = True
                    logger.info("workspace_templates.repaired file=%s agent=%s", filename, agent_id)
                except Exception as exc:
                    results[filename]["repair_error"] = str(exc)

    return results
