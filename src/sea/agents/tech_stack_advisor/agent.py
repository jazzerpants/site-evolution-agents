"""4G Tech Stack Advisor Agent — tiered tech recommendations per feature."""

from __future__ import annotations

import json
import logging
from typing import Any

from sea.agents.base import BaseAgent, extract_json
from sea.agents.tech_stack_advisor.prompts import SYSTEM_PROMPT
from sea.agents.tech_stack_advisor.tools import TOOLS, make_tool_handler
from sea.schemas.code_analysis import CodeAnalysisOutput
from sea.schemas.recommendations import Pass1Output
from sea.schemas.tech_stack import TechStackAdvisorOutput
from sea.shared.claude_client import ClaudeClient, ToolHandler, TokensCallback
from sea.shared.codebase_reader import CodebaseReader

logger = logging.getLogger(__name__)


class TechStackAdvisorAgent(BaseAgent):
    """Agent 4G — produces tiered tech stack recommendations for specific features.

    For each feature it evaluates:
    - A simple approach (minimal deps, fits current stack)
    - A comprehensive approach (best-practice, possibly more deps/arch changes)
    - Architecture fit assessment
    - Effort estimate and recommended approach
    """

    def __init__(self, client: ClaudeClient, reader: CodebaseReader) -> None:
        super().__init__(client)
        self._reader = reader
        self._tool_handler = make_tool_handler(reader)

    @property
    def name(self) -> str:
        return "4G Tech Stack Advisor"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[dict[str, Any]]:
        return TOOLS

    def get_tool_handler(self) -> ToolHandler:
        return self._tool_handler

    def parse_output(self, raw_text: str) -> TechStackAdvisorOutput:
        data = extract_json(raw_text)
        return TechStackAdvisorOutput(**data)

    async def run_evaluation(
        self,
        features: list[str],
        code_analysis: CodeAnalysisOutput | None = None,
        pass1: Pass1Output | None = None,
        *,
        on_progress: Any | None = None,
        on_event: Any | None = None,
        on_tokens: TokensCallback | None = None,
    ) -> TechStackAdvisorOutput:
        """Evaluate tech stack options for a list of features.

        Processes one feature at a time to avoid output token limits — each
        feature requires 2-3 Mermaid diagrams which quickly exhausts the
        model's output budget when batched together.

        ``features`` is a list of feature name strings (e.g. ["search", "auth"]).
        If ``pass1`` is provided, parity_source data is extracted for each feature
        from parity_gap recommendations.

        ``code_analysis`` provides the tech stack summary to seed the evaluation.
        """
        # Build parity context: feature_name -> list of competitor names
        parity_context: dict[str, list[str]] = {}
        if pass1:
            for rec in pass1.recommendations:
                if rec.parity_gap and rec.competitors_with_feature:
                    key = rec.title.lower()
                    parity_context[key] = rec.competitors_with_feature

        # Build stack context once — reused for every feature
        stack_context: dict[str, Any] = {}
        if code_analysis:
            stack_context = {
                "tech_stack": code_analysis.model_dump().get("tech_stack", []),
                "architecture": code_analysis.model_dump().get("architecture", {}),
                "summary": code_analysis.model_dump().get("summary", ""),
            }

        # Evaluate one feature at a time to stay within output token limits
        from sea.schemas.tech_stack import TechStackRecommendation
        all_features: list[TechStackRecommendation] = []

        for i, f in enumerate(features):
            if on_progress:
                on_progress(f"Feature {i + 1}/{len(features)}: {f}")

            entry: dict[str, Any] = {"feature_name": f}
            for key, competitors in parity_context.items():
                if f.lower() in key or key in f.lower():
                    entry["parity_source"] = competitors
                    break

            input_data: dict[str, Any] = {"features_to_evaluate": [entry]}
            if stack_context:
                input_data["current_stack"] = stack_context

            messages = [{"role": "user", "content": json.dumps(input_data, indent=2)}]
            raw = await self.client.run_agent_loop(
                system=self.get_system_prompt(),
                messages=messages,
                tools=self.get_tools(),
                tool_handler=self._tool_handler,
                on_progress=on_progress,
                on_tokens=on_tokens,
            )
            result = await self._parse_with_retry(
                raw, messages, on_progress=on_progress, on_event=on_event, on_tokens=on_tokens,
            )
            all_features.extend(result.features)

        return TechStackAdvisorOutput(
            features=all_features,
            summary=f"Evaluated {len(all_features)} feature(s).",
        )
