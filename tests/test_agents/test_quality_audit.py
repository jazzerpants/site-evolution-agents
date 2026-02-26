"""Tests for the 4E Quality Audit agent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from sea.agents.quality_audit.agent import QualityAuditAgent
from sea.agents.quality_audit.tools import TOOLS, make_tool_handler
from sea.schemas.quality import (
    QualityAuditOutput,
    AccessibilityReport,
    PerformanceReport,
    AccessibilityIssue,
    PerformanceMetric,
    QualityIssue,
)
from sea.shared.browser import BrowserManager
from sea.shared.claude_client import ClaudeClient


SAMPLE_OUTPUT = {
    "accessibility": {
        "wcag_level": "AA",
        "issues": [
            {
                "description": "Image missing alt text",
                "severity": "serious",
                "wcag_criterion": "1.1.1",
                "element": "<img src='hero.jpg'>",
                "suggestion": "Add descriptive alt attribute",
            }
        ],
        "keyboard_navigation": "Tab order is logical but skip-nav link is missing",
        "screen_reader_notes": "Headings are well-structured",
        "aria_usage": "Minimal ARIA usage, relies on semantic HTML",
    },
    "performance": {
        "metrics": [
            {"name": "LCP", "value": "2.1s", "rating": "good", "notes": ""},
            {"name": "FCP", "value": "1.2s", "rating": "good", "notes": ""},
            {"name": "CLS", "value": "0.12", "rating": "needs-improvement", "notes": "Layout shift from images"},
        ],
        "bundle_analysis": "Total JS: 250KB gzipped",
        "image_optimization": "No WebP images, no lazy loading",
        "caching_strategy": "Basic browser caching only",
        "critical_rendering_path": "Render-blocking CSS in head",
    },
    "priority_issues": [
        {
            "description": "Missing alt text on hero images",
            "category": "accessibility",
            "impact": "high",
            "effort_to_fix": "1 hour",
        },
        {
            "description": "Layout shift from unoptimized images",
            "category": "performance",
            "impact": "medium",
            "effort_to_fix": "2-3 hours",
        },
    ],
    "summary": "Good performance with some accessibility gaps.",
}


class TestQualityAuditSchema:
    def test_parse_full_output(self) -> None:
        output = QualityAuditOutput(**SAMPLE_OUTPUT)
        assert output.accessibility.wcag_level == "AA"
        assert len(output.accessibility.issues) == 1
        assert len(output.performance.metrics) == 3
        assert len(output.priority_issues) == 2

    def test_round_trip(self) -> None:
        output = QualityAuditOutput(**SAMPLE_OUTPUT)
        restored = QualityAuditOutput.model_validate_json(output.model_dump_json())
        assert restored.performance.metrics[0].name == "LCP"

    def test_minimal(self) -> None:
        output = QualityAuditOutput(summary="empty")
        assert output.accessibility.issues == []
        assert output.performance.metrics == []


class TestQualityAuditTools:
    def test_tools_have_required_fields(self) -> None:
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_expected_tools(self) -> None:
        names = {t["name"] for t in TOOLS}
        assert names == {"run_axe", "measure_vitals", "screenshot", "read_file", "search_code"}

    @pytest.mark.asyncio
    async def test_unknown_tool(self) -> None:
        browser = MagicMock(spec=BrowserManager)
        handler = make_tool_handler(browser)
        result = await handler("nonexistent", {})
        assert "Unknown tool" in result

    @pytest.mark.asyncio
    async def test_read_file_without_reader(self) -> None:
        browser = MagicMock(spec=BrowserManager)
        handler = make_tool_handler(browser, reader=None)
        result = await handler("read_file", {"path": "test.txt"})
        assert "not available" in result


class TestQualityAuditAgent:
    def test_parse_output(self) -> None:
        client = ClaudeClient.__new__(ClaudeClient)
        browser = MagicMock(spec=BrowserManager)
        agent = QualityAuditAgent(client=client, browser=browser)

        output = agent.parse_output(json.dumps(SAMPLE_OUTPUT))
        assert isinstance(output, QualityAuditOutput)
        assert output.accessibility.wcag_level == "AA"

    def test_name(self) -> None:
        client = ClaudeClient.__new__(ClaudeClient)
        browser = MagicMock(spec=BrowserManager)
        agent = QualityAuditAgent(client=client, browser=browser)
        assert agent.name == "4E Quality Audit"
