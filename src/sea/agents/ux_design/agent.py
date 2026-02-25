"""4F UX Design Audit Agent — visual UX evaluation from screenshots."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from sea.agents.base import BaseAgent, extract_json
from sea.agents.ux_design.prompts import SYSTEM_PROMPT
from sea.schemas.ux_design import UXDesignOutput
from sea.shared.claude_client import ClaudeClient, ToolHandler

logger = logging.getLogger(__name__)

_JSON_RETRY_MSG = (
    "Your analysis is excellent, but I need the output as a single "
    "JSON object (no markdown, no explanation — just raw JSON) "
    "matching the schema described in your instructions. "
    "Please re-format your response now."
)


class UXDesignAgent(BaseAgent):
    """Agent 4F — evaluates UX/design quality from screenshots.

    This agent has no tools — it receives screenshots as image content
    blocks and produces a structured visual design assessment. Uses
    ``vision_completion`` instead of the agentic tool loop.
    """

    def __init__(self, client: ClaudeClient) -> None:
        super().__init__(client)

    @property
    def name(self) -> str:
        return "4F UX Design Audit"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[dict[str, Any]]:
        return []  # Pure vision analysis, no tools

    def get_tool_handler(self) -> ToolHandler:
        async def noop(name: str, input: dict) -> str:
            return ""
        return noop

    def parse_output(self, raw_text: str) -> UXDesignOutput:
        data = extract_json(raw_text)
        return UXDesignOutput(**data)

    async def run_audit(
        self,
        screenshots: list[dict[str, Any]],
        *,
        research_summary: str = "",
        code_analysis_summary: str = "",
        quality_summary: str = "",
        design_system_info: str = "",
        on_progress: Any | None = None,
        on_event: Any | None = None,
    ) -> UXDesignOutput:
        """Run the UX design audit on collected screenshots.

        Parameters
        ----------
        screenshots:
            List of ``ScreenshotEntry`` dicts with ``url`` and ``tiles``
            (list of base64 JPEG strings).
        research_summary:
            Summary from the comparative research agent.
        code_analysis_summary:
            Summary from the code analysis agent.
        quality_summary:
            Summary from the quality audit agent.
        design_system_info:
            Design system information from code analysis.
        """
        if on_progress:
            on_progress("Building vision prompt…")

        content_parts = self._build_content_parts(
            screenshots,
            research_summary=research_summary,
            code_analysis_summary=code_analysis_summary,
            quality_summary=quality_summary,
            design_system_info=design_system_info,
        )

        if on_progress:
            on_progress("Analyzing screenshots…")

        raw = await self.client.vision_completion(
            system=self.get_system_prompt(),
            content=content_parts,
        )

        logger.debug("Agent %s raw output:\n%s", self.name, raw[:500])

        try:
            return self.parse_output(raw)
        except (ValueError, json.JSONDecodeError, KeyError) as first_err:
            logger.warning(
                "Agent %s output was not valid JSON, requesting re-format. Error: %s",
                self.name, first_err,
            )

        if on_progress:
            on_progress("Re-formatting output as JSON…")
        if on_event:
            on_event("[yellow]Output was not valid JSON — requesting re-format[/]")

        # Retry: ask the model to re-format
        retry_content: list[dict[str, Any]] = [
            {"type": "text", "text": raw},
            {"type": "text", "text": _JSON_RETRY_MSG},
        ]

        raw_retry = await self.client.vision_completion(
            system=self.get_system_prompt(),
            content=retry_content,
        )

        try:
            result = self.parse_output(raw_retry)
        except (ValueError, json.JSONDecodeError, KeyError):
            if on_event:
                on_event("[red]Re-format also failed — could not parse JSON[/]")
            raise
        if on_event:
            on_event("[green]Re-format succeeded — valid JSON on retry[/]")
        return result

    def _build_content_parts(
        self,
        screenshots: list[dict[str, Any]],
        *,
        research_summary: str,
        code_analysis_summary: str,
        quality_summary: str,
        design_system_info: str,
    ) -> list[dict[str, Any]]:
        """Build multipart content with text context and screenshot images."""
        parts: list[dict[str, Any]] = []

        # Introductory text
        parts.append({
            "type": "text",
            "text": (
                "Evaluate the UX and visual design of the target site based on "
                "the screenshots below. Compare against competitor screenshots "
                "where available."
            ),
        })

        # Context from other agents
        context_parts = []
        if research_summary:
            context_parts.append(f"Research summary: {research_summary}")
        if code_analysis_summary:
            context_parts.append(f"Code analysis: {code_analysis_summary}")
        if quality_summary:
            context_parts.append(f"Quality audit: {quality_summary}")
        if design_system_info:
            context_parts.append(f"Design system: {design_system_info}")

        if context_parts:
            parts.append({
                "type": "text",
                "text": "## Context from prior analysis\n" + "\n\n".join(context_parts),
            })

        # Screenshots — send first 2 tiles per URL at detail=low
        max_tiles_per_url = 2
        for entry in screenshots:
            url = entry.get("url", "unknown")
            tiles = entry.get("tiles", [])
            if not tiles:
                continue

            tiles_to_send = tiles[:max_tiles_per_url]
            parts.append({
                "type": "text",
                "text": f"[Screenshot: {url}] ({len(tiles_to_send)} of {len(tiles)} sections)",
            })
            for i, tile_b64 in enumerate(tiles_to_send):
                parts.append({
                    "type": "text",
                    "text": f"[Section {i + 1}/{len(tiles)}, y={i * 800}px]",
                })
                parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{tile_b64}",
                        "detail": "low",
                    },
                })

        if len(parts) <= 1:
            # No screenshots were added — add a note
            parts.append({
                "type": "text",
                "text": (
                    "No screenshots are available. Provide your best assessment "
                    "based on the context from other agents."
                ),
            })

        return parts
