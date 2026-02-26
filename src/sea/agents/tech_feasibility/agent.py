"""4D Technology Feasibility Agent — evaluates implementation feasibility."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from sea.agents.base import BaseAgent, extract_json
from sea.agents.tech_feasibility.prompts import FOLLOWUP_SYSTEM_PROMPT, SYSTEM_PROMPT
from sea.agents.tech_feasibility.tools import TOOLS, make_tool_handler
from sea.schemas.code_analysis import CodeAnalysisOutput
from sea.schemas.config import Constraints
from sea.schemas.feasibility import FeasibilityOutput
from sea.schemas.recommendations import Pass1Output
from sea.shared.claude_client import ClaudeClient, ToolHandler, TokensCallback
from sea.shared.codebase_reader import CodebaseReader

logger = logging.getLogger(__name__)


class TechFeasibilityAgent(BaseAgent):
    """Agent 4D — assesses feasibility of recommended features."""

    def __init__(self, client: ClaudeClient, reader: CodebaseReader) -> None:
        super().__init__(client)
        self._reader = reader
        self._tool_handler = make_tool_handler(reader)

    @property
    def name(self) -> str:
        return "4D Tech Feasibility"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[dict[str, Any]]:
        return TOOLS

    def get_tool_handler(self) -> ToolHandler:
        return self._tool_handler

    def parse_output(self, raw_text: str) -> FeasibilityOutput:
        data = extract_json(raw_text)
        return FeasibilityOutput(**data)

    async def run_assessment(
        self,
        pass1: Pass1Output | None,
        code_analysis: CodeAnalysisOutput | None,
        constraints: Constraints | None = None,
        *,
        on_progress: Any | None = None,
        on_event: Any | None = None,
        on_tokens: TokensCallback | None = None,
    ) -> FeasibilityOutput:
        """Run feasibility assessment on Pass 1 recommendations."""
        input_data: dict[str, Any] = {}
        if pass1:
            input_data["recommendations"] = pass1.model_dump()
        if code_analysis:
            # Only pass the fields 4D needs — not the full analysis blob
            input_data["code_context"] = {
                "tech_stack": code_analysis.model_dump().get("tech_stack", []),
                "architecture": code_analysis.model_dump().get("architecture", {}),
                "summary": code_analysis.model_dump().get("summary", ""),
            }
        if constraints:
            input_data["constraints"] = constraints.model_dump()

        user_message = json.dumps(input_data, indent=2)

        messages = [{"role": "user", "content": user_message}]
        raw = await self.client.run_agent_loop(
            system=self.get_system_prompt(),
            messages=messages,
            tools=self.get_tools(),
            tool_handler=self._tool_handler,
            on_progress=on_progress,
            on_tokens=on_tokens,
        )
        return await self._parse_with_retry(
            raw, messages, on_progress=on_progress, on_event=on_event, on_tokens=on_tokens,
        )

    async def run_followup(
        self,
        question: str,
        code_analysis: CodeAnalysisOutput | None = None,
        *,
        on_progress: Any | None = None,
        on_tokens: TokensCallback | None = None,
    ) -> str:
        """Assess an ad-hoc feature idea against the codebase. Returns plain-text answer."""
        input_data: dict[str, Any] = {"question": question}
        if code_analysis:
            input_data["code_context"] = {
                "tech_stack": code_analysis.model_dump().get("tech_stack", []),
                "architecture": code_analysis.model_dump().get("architecture", {}),
                "summary": code_analysis.model_dump().get("summary", ""),
            }
        user_message = json.dumps(input_data, indent=2)
        raw = await self.client.run_agent_loop(
            system=FOLLOWUP_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            tools=self.get_tools(),
            tool_handler=self._tool_handler,
            on_progress=on_progress,
            on_tokens=on_tokens,
        )
        return raw.strip()
