"""4E Quality Audit Agent — accessibility and performance auditing."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from sea.agents.base import BaseAgent, extract_json
from sea.agents.quality_audit.prompts import SYSTEM_PROMPT
from sea.agents.quality_audit.tools import TOOLS, make_tool_handler
from sea.schemas.code_analysis import CodeAnalysisOutput
from sea.schemas.quality import QualityAuditOutput
from sea.shared.browser import BrowserManager
from sea.shared.claude_client import ClaudeClient, ToolHandler
from sea.shared.codebase_reader import CodebaseReader

logger = logging.getLogger(__name__)


class QualityAuditAgent(BaseAgent):
    """Agent 4E — audits accessibility and performance."""

    def __init__(
        self,
        client: ClaudeClient,
        browser: BrowserManager,
        reader: CodebaseReader | None = None,
    ) -> None:
        super().__init__(client)
        self._browser = browser
        self._reader = reader
        self._tool_handler = make_tool_handler(browser, reader)

    @property
    def name(self) -> str:
        return "4E Quality Audit"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[dict[str, Any]]:
        return TOOLS

    def get_tool_handler(self) -> ToolHandler:
        return self._tool_handler

    def parse_output(self, raw_text: str) -> QualityAuditOutput:
        data = extract_json(raw_text)
        return QualityAuditOutput(**data)

    async def run_audit(
        self,
        url: str,
        code_analysis: CodeAnalysisOutput | None = None,
        *,
        on_progress: Any | None = None,
        on_event: Any | None = None,
    ) -> QualityAuditOutput:
        """Run the quality audit on a URL."""
        # 4E runs its own audits (axe, vitals, screenshots) — it only needs
        # the URL and a brief tech context, not the full code analysis blob.
        parts = [f"Audit the following URL for accessibility and performance: {url}"]
        if code_analysis:
            parts.append(f"Tech stack: {', '.join(t.name for t in code_analysis.tech_stack)}")
            if code_analysis.summary:
                parts.append(f"Codebase summary: {code_analysis.summary}")

        user_message = "\n\n".join(parts)

        messages = [{"role": "user", "content": user_message}]
        raw = await self.client.run_agent_loop(
            system=self.get_system_prompt(),
            messages=messages,
            tools=self.get_tools(),
            tool_handler=self._tool_handler,
            on_progress=on_progress,
        )
        return await self._parse_with_retry(
            raw, messages, on_progress=on_progress, on_event=on_event,
        )
