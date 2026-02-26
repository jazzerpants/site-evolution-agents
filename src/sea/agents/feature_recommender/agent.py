"""4C Feature Recommender Agent — two-pass recommendation engine."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from sea.agents.base import BaseAgent, extract_json
from sea.agents.feature_recommender.prompts import PASS1_SYSTEM_PROMPT, PASS2_SYSTEM_PROMPT
from sea.schemas.code_analysis import CodeAnalysisOutput
from sea.schemas.feasibility import FeasibilityOutput
from sea.schemas.quality import QualityAuditOutput
from sea.schemas.recommendations import Pass1Output, Pass2Output
from sea.schemas.research import ComparativeResearchOutput
from sea.shared.claude_client import ClaudeClient, ToolHandler, TokensCallback

logger = logging.getLogger(__name__)

_JSON_RETRY_MSG = (
    "Your analysis is excellent, but I need the output as a single "
    "JSON object (no markdown, no explanation — just raw JSON) "
    "matching the schema described in your instructions. "
    "Please re-format your response now."
)


class FeatureRecommenderAgent(BaseAgent):
    """Agent 4C — synthesizes research + code analysis into recommendations.

    This agent has no tools — it uses simple_completion (no tool loop).
    It runs in two passes with different inputs and prompts.
    """

    def __init__(self, client: ClaudeClient) -> None:
        super().__init__(client)

    @property
    def name(self) -> str:
        return "4C Feature Recommender"

    def get_system_prompt(self) -> str:
        return PASS1_SYSTEM_PROMPT

    def get_tools(self) -> list[dict[str, Any]]:
        return []  # No tools — pure synthesis

    def get_tool_handler(self) -> ToolHandler:
        async def noop(name: str, input: dict) -> str:
            return ""
        return noop

    def parse_output(self, raw_text: str) -> BaseModel:
        raise NotImplementedError("Use run_pass1 or run_pass2 instead")

    async def _simple_with_retry(
        self,
        system: str,
        user_message: str,
        parse_fn,
        on_tokens: TokensCallback | None = None,
    ):
        """Call simple_completion, parse, and retry once if JSON parsing fails."""
        raw = await self.client.simple_completion(
            system=system,
            user_message=user_message,
            on_tokens=on_tokens,
        )
        try:
            return parse_fn(raw)
        except (ValueError, json.JSONDecodeError, KeyError) as err:
            logger.warning(
                "Agent %s output was not valid JSON, requesting re-format. Error: %s",
                self.name, err,
            )

        # Retry: feed the original output back and ask for JSON
        retry_msg = f"{user_message}\n\nAssistant's previous response:\n{raw}\n\n{_JSON_RETRY_MSG}"
        raw_retry = await self.client.simple_completion(
            system=system,
            user_message=retry_msg,
            on_tokens=on_tokens,
        )
        return parse_fn(raw_retry)

    async def run_pass1(
        self,
        research: ComparativeResearchOutput,
        code_analysis: CodeAnalysisOutput,
        priorities: list[str],
        *,
        on_progress: Any | None = None,
        on_tokens: TokensCallback | None = None,
    ) -> Pass1Output:
        """Pass 1: Initial ranking from research + code analysis."""
        # Slim research: drop redundant per-competitor features, design_systems
        research_slim = research.model_dump()
        for comp in research_slim.get("competitors", []):
            comp.pop("features", None)
        research_slim.pop("design_systems", None)

        # Slim code analysis: drop mermaid diagram, trim components to name+path
        ca_slim = code_analysis.model_dump()
        arch = ca_slim.get("architecture", {})
        if arch:
            arch.pop("mermaid_diagram", None)
        ca_slim["components"] = [
            {"name": c["name"], "file_path": c["file_path"]}
            for c in ca_slim.get("components", [])
            if "name" in c and "file_path" in c
        ]

        user_message = json.dumps(
            {
                "research": research_slim,
                "code_analysis": ca_slim,
                "user_priorities": priorities,
            },
        )

        def parse(raw: str) -> Pass1Output:
            return Pass1Output(**extract_json(raw))

        return await self._simple_with_retry(PASS1_SYSTEM_PROMPT, user_message, parse, on_tokens=on_tokens)

    async def run_pass2(
        self,
        pass1: Pass1Output,
        feasibility: FeasibilityOutput,
        quality_audit: QualityAuditOutput,
        *,
        on_progress: Any | None = None,
        on_tokens: TokensCallback | None = None,
    ) -> Pass2Output:
        """Pass 2: Re-rank with feasibility + quality data."""
        # Slim pass1: keep only key fields per recommendation
        p1 = pass1.model_dump()
        p1_slim = {
            "recommendations": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "category": r["category"],
                    "rank": r.get("rank"),
                    "scores": r.get("scores"),
                }
                for r in p1.get("recommendations", [])
            ],
            "quick_wins": p1.get("quick_wins", []),
            "summary": p1.get("summary", ""),
        }

        # Slim quality_audit: keep only priority_issues and summary
        qa = quality_audit.model_dump()
        qa_slim = {
            "priority_issues": qa.get("priority_issues", []),
            "summary": qa.get("summary", ""),
        }

        user_message = json.dumps(
            {
                "pass1_recommendations": p1_slim,
                "feasibility": feasibility.model_dump(),
                "quality_audit": qa_slim,
            },
        )

        def parse(raw: str) -> Pass2Output:
            return Pass2Output(**extract_json(raw))

        return await self._simple_with_retry(PASS2_SYSTEM_PROMPT, user_message, parse, on_tokens=on_tokens)
