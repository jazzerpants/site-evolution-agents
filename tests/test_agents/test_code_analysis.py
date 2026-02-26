"""Tests for the 4B Code Analysis agent."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from sea.agents.code_analysis.agent import CodeAnalysisAgent
from sea.agents.code_analysis.tools import TOOLS, make_tool_handler
from sea.agents.base import extract_json
from sea.schemas.code_analysis import CodeAnalysisOutput
from sea.shared.codebase_reader import CodebaseReader
from sea.shared.claude_client import ClaudeClient


# Sample valid output JSON that Claude would return
SAMPLE_OUTPUT = {
    "tech_stack": [
        {
            "name": "Next.js",
            "category": "framework",
            "version": "16.0",
            "ux_pros": ["SSR", "Fast navigation"],
            "ux_cons": ["Complex config"],
        }
    ],
    "architecture": {
        "routing_pattern": "App Router",
        "data_flow": "Server Components → Client Components",
        "component_tree_summary": "App shell with nested routes",
        "mermaid_diagram": "graph TD; A-->B;",
    },
    "components": [
        {"name": "Header", "file_path": "src/components/Header.tsx", "description": "Site header", "has_tests": False}
    ],
    "tech_debt": [
        {"description": "No error boundaries", "severity": "medium", "location": "src/", "suggestion": "Add error boundaries"}
    ],
    "extensibility": {
        "overall_score": "medium",
        "strengths": ["Component-based"],
        "weaknesses": ["Tight coupling"],
        "notes": "",
    },
    "design_system": {
        "has_design_system": False,
        "semantic_tokens": [],
        "theming_support": "none",
        "animation_patterns": [],
        "component_library": "",
    },
    "bundle_notes": "Small bundle",
    "summary": "A Next.js application with standard patterns.",
}


class TestExtractJson:
    """Test the JSON extraction helper."""

    def test_plain_json(self) -> None:
        data = extract_json(json.dumps({"key": "value"}))
        assert data["key"] == "value"

    def test_json_in_markdown_fence(self) -> None:
        text = 'Some text\n```json\n{"key": "value"}\n```\nMore text'
        data = extract_json(text)
        assert data["key"] == "value"

    def test_json_surrounded_by_text(self) -> None:
        text = 'Here is my analysis:\n{"key": "value"}\nDone!'
        data = extract_json(text)
        assert data["key"] == "value"


class TestCodeAnalysisOutputSchema:
    """Test parsing output JSON into the Pydantic model."""

    def test_parse_full_output(self) -> None:
        output = CodeAnalysisOutput(**SAMPLE_OUTPUT)
        assert output.tech_stack[0].name == "Next.js"
        assert output.architecture.routing_pattern == "App Router"
        assert len(output.tech_debt) == 1

    def test_parse_minimal_output(self) -> None:
        minimal = {"tech_stack": [], "architecture": {}, "summary": "empty"}
        output = CodeAnalysisOutput(**minimal)
        assert output.tech_stack == []
        assert output.summary == "empty"

    def test_round_trip(self) -> None:
        output = CodeAnalysisOutput(**SAMPLE_OUTPUT)
        restored = CodeAnalysisOutput.model_validate_json(output.model_dump_json())
        assert restored.tech_stack[0].name == "Next.js"


class TestCodeAnalysisTools:
    """Test the tool definitions and handler."""

    @pytest.fixture
    def reader(self, tmp_path: Path) -> CodebaseReader:
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.ts").write_text("export default function App() {}")
        return CodebaseReader(tmp_path)

    def test_tools_have_required_fields(self) -> None:
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    @pytest.mark.asyncio
    async def test_list_dir(self, reader: CodebaseReader) -> None:
        handler = make_tool_handler(reader)
        result = await handler("list_dir", {"path": "."})
        assert "package.json" in result
        assert "src/" in result

    @pytest.mark.asyncio
    async def test_read_file(self, reader: CodebaseReader) -> None:
        handler = make_tool_handler(reader)
        result = await handler("read_file", {"path": "src/index.ts"})
        assert "export default" in result

    @pytest.mark.asyncio
    async def test_search_code(self, reader: CodebaseReader) -> None:
        handler = make_tool_handler(reader)
        result = await handler("search_code", {"pattern": "export"})
        assert "index.ts" in result

    @pytest.mark.asyncio
    async def test_get_tree(self, reader: CodebaseReader) -> None:
        handler = make_tool_handler(reader)
        result = await handler("get_tree", {})
        assert "src/" in result

    @pytest.mark.asyncio
    async def test_read_manifest(self, reader: CodebaseReader) -> None:
        handler = make_tool_handler(reader)
        result = await handler("read_manifest", {})
        assert "package.json" in result

    @pytest.mark.asyncio
    async def test_unknown_tool(self, reader: CodebaseReader) -> None:
        handler = make_tool_handler(reader)
        result = await handler("nonexistent", {})
        assert "Unknown tool" in result


class TestCodeAnalysisAgent:
    """Test the agent's parse_output method (no API calls)."""

    def test_parse_output(self) -> None:
        client = ClaudeClient.__new__(ClaudeClient)
        reader_mock = MagicMock(spec=CodebaseReader)
        agent = CodeAnalysisAgent(client=client, reader=reader_mock)

        raw_text = json.dumps(SAMPLE_OUTPUT)
        output = agent.parse_output(raw_text)
        assert isinstance(output, CodeAnalysisOutput)
        assert output.tech_stack[0].name == "Next.js"

    def test_parse_output_with_markdown_fence(self) -> None:
        client = ClaudeClient.__new__(ClaudeClient)
        reader_mock = MagicMock(spec=CodebaseReader)
        agent = CodeAnalysisAgent(client=client, reader=reader_mock)

        raw_text = f"```json\n{json.dumps(SAMPLE_OUTPUT)}\n```"
        output = agent.parse_output(raw_text)
        assert isinstance(output, CodeAnalysisOutput)
