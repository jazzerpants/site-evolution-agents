"""Tests for the 4A Comparative Research agent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from sea.agents.comparative_research.agent import ComparativeResearchAgent
from sea.agents.comparative_research.tools import TOOLS, PAGE_BUDGET, make_tool_handler
from sea.schemas.research import ComparativeResearchOutput
from sea.shared.browser import BrowserManager
from sea.shared.claude_client import ClaudeClient


SAMPLE_OUTPUT = {
    "competitors": [
        {
            "name": "Dev.to",
            "url": "https://dev.to",
            "relevance": "Similar content platform",
            "strengths": ["Great community", "Fast"],
            "weaknesses": ["Cluttered"],
        },
        {
            "name": "Hashnode",
            "url": "https://hashnode.com",
            "relevance": "Developer blogging",
            "strengths": ["Custom domains"],
            "weaknesses": ["Smaller audience"],
        },
    ],
    "feature_matrix": [
        {
            "feature": "Dark mode",
            "current_site": "no",
            "competitors": {"Dev.to": "yes", "Hashnode": "yes"},
        },
    ],
    "ux_patterns": [
        {
            "name": "Infinite scroll",
            "description": "Content loads as you scroll",
            "seen_in": ["Dev.to"],
            "relevance": "Improves engagement",
        }
    ],
    "gaps": [
        {
            "description": "No dark mode support",
            "severity": "medium",
            "competitors_with_feature": ["Dev.to", "Hashnode"],
        }
    ],
    "trends": ["AI-powered content suggestions"],
    "design_systems": [
        {"name": "Tailwind CSS", "url": "https://tailwindcss.com", "notes": "Used by competitor"}
    ],
    "summary": "The target site is missing several key features present in competitors.",
}


class TestComparativeResearchSchema:
    """Test the research output Pydantic model."""

    def test_parse_full_output(self) -> None:
        output = ComparativeResearchOutput(**SAMPLE_OUTPUT)
        assert len(output.competitors) == 2
        assert output.competitors[0].name == "Dev.to"
        assert len(output.gaps) == 1

    def test_parse_minimal_output(self) -> None:
        minimal = {"competitors": [], "summary": "No competitors found"}
        output = ComparativeResearchOutput(**minimal)
        assert output.competitors == []

    def test_round_trip(self) -> None:
        output = ComparativeResearchOutput(**SAMPLE_OUTPUT)
        restored = ComparativeResearchOutput.model_validate_json(output.model_dump_json())
        assert restored.competitors[0].url == "https://dev.to"


class TestComparativeResearchTools:
    """Test the tool definitions."""

    def test_tools_have_required_fields(self) -> None:
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_expected_tools_exist(self) -> None:
        names = {t["name"] for t in TOOLS}
        assert names == {"browse_page", "discover_links", "screenshot", "extract_css", "ask_user"}

    @pytest.mark.asyncio
    async def test_tool_handler_unknown_tool(self) -> None:
        browser = MagicMock(spec=BrowserManager)
        handler = make_tool_handler(browser)
        result = await handler("nonexistent", {})
        assert "Unknown tool" in result


class TestPageBudget:
    """Verify that the page-visit budget is enforced per site_depth."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("site_depth,expected_budget", [(0, 10), (1, 25), (2, 50)])
    async def test_budget_matches_constant(self, site_depth: int, expected_budget: int) -> None:
        """PAGE_BUDGET dict contains the expected limits."""
        assert PAGE_BUDGET[site_depth] == expected_budget

    @pytest.mark.asyncio
    @pytest.mark.parametrize("site_depth", [0, 1, 2])
    async def test_browse_page_blocked_after_budget(self, site_depth: int) -> None:
        """browse_page returns an exhaustion message once the budget is spent."""
        browser = MagicMock(spec=BrowserManager)
        browser.get_page_text = AsyncMock(return_value="page text")
        handler = make_tool_handler(browser, site_depth=site_depth)

        budget = PAGE_BUDGET[site_depth]

        # Exhaust the budget
        for i in range(budget):
            result = await handler("browse_page", {"url": f"https://example.com/page{i}"})
            assert result == "page text", f"visit {i + 1} should succeed"

        # Next call should be refused
        result = await handler("browse_page", {"url": "https://example.com/over-budget"})
        assert "Page budget exhausted" in result
        assert f"{budget} pages" in result

        # Browser should NOT have been called for the over-budget request
        assert browser.get_page_text.call_count == budget

    @pytest.mark.asyncio
    async def test_screenshot_exempt_from_page_budget(self) -> None:
        """Screenshots have their own budget and don't consume from the page budget."""
        browser = MagicMock(spec=BrowserManager)
        browser.get_page_text = AsyncMock(return_value="text")
        browser.take_screenshot = AsyncMock(return_value=["tile1_b64"])
        browser.extract_css = AsyncMock(return_value='{"custom_properties":{}}')

        # Use depth 0 (budget=10) for a quick test
        handler = make_tool_handler(browser, site_depth=0)
        budget = PAGE_BUDGET[0]

        # Exhaust the page budget with browse_page + extract_css
        for i in range(budget):
            await handler("browse_page", {"url": f"https://a.com/{i}"})

        # browse_page and extract_css should now be blocked
        result = await handler("browse_page", {"url": "https://a.com/over"})
        assert "Page budget exhausted" in result
        result = await handler("extract_css", {"url": "https://a.com/over"})
        assert "Page budget exhausted" in result

        # But screenshots should still work (separate budget)
        result = await handler("screenshot", {"url": "https://a.com/still-works"})
        assert isinstance(result, list), "screenshot should still succeed"

    @pytest.mark.asyncio
    async def test_screenshot_budget_enforced(self) -> None:
        """Screenshots have their own MAX_SCREENSHOTS cap."""
        from sea.agents.comparative_research.tools import MAX_SCREENSHOTS

        browser = MagicMock(spec=BrowserManager)
        browser.take_screenshot = AsyncMock(return_value=["tile1_b64"])

        handler = make_tool_handler(browser, site_depth=0)

        # Exhaust the screenshot budget
        for i in range(MAX_SCREENSHOTS):
            result = await handler("screenshot", {"url": f"https://a.com/site{i}"})
            assert isinstance(result, list), f"screenshot {i + 1} should succeed"

        # Next screenshot should be refused
        result = await handler("screenshot", {"url": "https://a.com/over"})
        assert "Screenshot budget reached" in result
        assert browser.take_screenshot.call_count == MAX_SCREENSHOTS

    @pytest.mark.asyncio
    async def test_discover_links_does_not_count(self) -> None:
        """discover_links is free — it should never exhaust the budget."""
        browser = MagicMock(spec=BrowserManager)
        browser.discover_links = AsyncMock(return_value=[{"url": "https://a.com", "text": "link"}])
        browser.get_page_text = AsyncMock(return_value="text")

        handler = make_tool_handler(browser, site_depth=0)
        budget = PAGE_BUDGET[0]

        # Call discover_links far more times than the budget
        for i in range(budget + 20):
            result = await handler("discover_links", {"url": f"https://a.com/page{i}"})
            assert "Page budget exhausted" not in result

        # browse_page should still work — budget is untouched
        result = await handler("browse_page", {"url": "https://a.com/first"})
        assert result == "text"

    @pytest.mark.asyncio
    async def test_discover_links_shows_remaining_budget(self) -> None:
        """discover_links response includes how many page visits are left."""
        browser = MagicMock(spec=BrowserManager)
        browser.discover_links = AsyncMock(return_value=[])
        browser.get_page_text = AsyncMock(return_value="text")

        handler = make_tool_handler(browser, site_depth=0)
        budget = PAGE_BUDGET[0]

        # Before any visits, full budget remaining
        result = await handler("discover_links", {"url": "https://a.com"})
        assert f"[{budget} page visits remaining in budget]" in result

        # Use 3 visits
        for i in range(3):
            await handler("browse_page", {"url": f"https://a.com/{i}"})

        result = await handler("discover_links", {"url": "https://a.com"})
        assert f"[{budget - 3} page visits remaining in budget]" in result


class TestComparativeResearchAgent:
    """Test agent parse_output."""

    def test_parse_output(self) -> None:
        client = ClaudeClient.__new__(ClaudeClient)
        browser = MagicMock(spec=BrowserManager)
        agent = ComparativeResearchAgent(client=client, browser=browser)

        output = agent.parse_output(json.dumps(SAMPLE_OUTPUT))
        assert isinstance(output, ComparativeResearchOutput)
        assert output.competitors[0].name == "Dev.to"
