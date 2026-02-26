"""Tests for the 4D Tech Feasibility agent."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sea.agents.tech_feasibility.agent import TechFeasibilityAgent
from sea.agents.tech_feasibility.tools import TOOLS, make_tool_handler
from sea.schemas.feasibility import FeasibilityOutput, FeasibilityAssessment, ProCon
from sea.shared.codebase_reader import CodebaseReader
from sea.shared.claude_client import ClaudeClient


SAMPLE_OUTPUT = {
    "assessments": [
        {
            "recommendation_id": "REC-001",
            "rating": "easy",
            "cost_estimate": "small",
            "developer_days": "1-2 days",
            "new_dependencies": ["next-themes"],
            "migration_path": "",
            "risk": "low",
            "pros": [{"point": "Easy to implement", "weight": "major"}],
            "cons": [{"point": "Adds bundle size", "weight": "minor"}],
            "notes": "Use next-themes package",
        },
        {
            "recommendation_id": "REC-002",
            "rating": "moderate",
            "cost_estimate": "medium",
            "developer_days": "5-7 days",
            "new_dependencies": [],
            "migration_path": "",
            "risk": "medium",
            "pros": [{"point": "Better mobile UX", "weight": "major"}],
            "cons": [{"point": "Requires design work", "weight": "moderate"}],
            "notes": "",
        },
    ],
    "summary": "Both recommendations are feasible with current stack.",
}


class TestFeasibilitySchema:
    def test_parse_full_output(self) -> None:
        output = FeasibilityOutput(**SAMPLE_OUTPUT)
        assert len(output.assessments) == 2
        assert output.assessments[0].rating == "easy"
        assert output.assessments[0].pros[0].point == "Easy to implement"

    def test_round_trip(self) -> None:
        output = FeasibilityOutput(**SAMPLE_OUTPUT)
        restored = FeasibilityOutput.model_validate_json(output.model_dump_json())
        assert restored.assessments[0].new_dependencies == ["next-themes"]

    def test_minimal(self) -> None:
        output = FeasibilityOutput(assessments=[], summary="empty")
        assert output.assessments == []


class TestFeasibilityTools:
    def test_tools_have_required_fields(self) -> None:
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_expected_tools(self) -> None:
        names = {t["name"] for t in TOOLS}
        assert names == {"read_file", "search_code"}

    @pytest.fixture
    def reader(self, tmp_path: Path) -> CodebaseReader:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.tsx").write_text("export default function App() {}")
        return CodebaseReader(tmp_path)

    @pytest.mark.asyncio
    async def test_read_file(self, reader: CodebaseReader) -> None:
        handler = make_tool_handler(reader)
        result = await handler("read_file", {"path": "src/app.tsx"})
        assert "export default" in result

    @pytest.mark.asyncio
    async def test_search_code(self, reader: CodebaseReader) -> None:
        handler = make_tool_handler(reader)
        result = await handler("search_code", {"pattern": "function"})
        assert "app.tsx" in result


class TestTechFeasibilityAgent:
    def test_parse_output(self) -> None:
        client = ClaudeClient.__new__(ClaudeClient)
        reader = MagicMock(spec=CodebaseReader)
        agent = TechFeasibilityAgent(client=client, reader=reader)

        output = agent.parse_output(json.dumps(SAMPLE_OUTPUT))
        assert isinstance(output, FeasibilityOutput)
        assert len(output.assessments) == 2
