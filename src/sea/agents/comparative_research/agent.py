"""4A Comparative Research Agent — browser-based competitor analysis."""

from __future__ import annotations

from typing import Any

from sea.agents.base import BaseAgent, extract_json
from sea.agents.comparative_research.prompts import SYSTEM_PROMPT
from sea.agents.comparative_research.tools import TOOLS, make_tool_handler
from sea.schemas.research import ComparativeResearchOutput
from sea.shared.browser import BrowserManager
from sea.shared.claude_client import ClaudeClient, ToolHandler


class ComparativeResearchAgent(BaseAgent):
    """Agent 4A — analyzes competitor websites via browser."""

    def __init__(self, client: ClaudeClient, browser: BrowserManager, *, site_depth: int = 1) -> None:
        super().__init__(client)
        self._browser = browser
        self._tool_handler = make_tool_handler(browser, site_depth=site_depth)

    @property
    def name(self) -> str:
        return "4A Comparative Research"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[dict[str, Any]]:
        return TOOLS

    def get_tool_handler(self) -> ToolHandler:
        return self._tool_handler

    def parse_output(self, raw_text: str) -> ComparativeResearchOutput:
        data = extract_json(raw_text)
        return ComparativeResearchOutput(**data)
