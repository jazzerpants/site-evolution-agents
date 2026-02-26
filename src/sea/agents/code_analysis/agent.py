"""4B Code Analysis Agent — analyzes a local codebase."""

from __future__ import annotations

from typing import Any

from sea.agents.base import BaseAgent, extract_json
from sea.agents.code_analysis.prompts import SYSTEM_PROMPT
from sea.agents.code_analysis.tools import TOOLS, make_tool_handler
from sea.schemas.code_analysis import CodeAnalysisOutput
from sea.shared.claude_client import ClaudeClient, ToolHandler
from sea.shared.codebase_reader import CodebaseReader


class CodeAnalysisAgent(BaseAgent):
    """Agent 4B — analyzes the local codebase for architecture, tech stack, etc."""

    def __init__(self, client: ClaudeClient, reader: CodebaseReader) -> None:
        super().__init__(client)
        self._reader = reader
        self._tool_handler = make_tool_handler(reader)

    @property
    def name(self) -> str:
        return "4B Code Analysis"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[dict[str, Any]]:
        return TOOLS

    def get_tool_handler(self) -> ToolHandler:
        return self._tool_handler

    def parse_output(self, raw_text: str) -> CodeAnalysisOutput:
        data = extract_json(raw_text)
        return CodeAnalysisOutput(**data)
