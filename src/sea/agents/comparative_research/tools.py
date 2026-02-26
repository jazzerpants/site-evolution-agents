"""Tool definitions and handler for the 4A Comparative Research agent."""

from __future__ import annotations

import json
import logging
from typing import Any

from sea.shared.browser import BrowserManager
from sea.shared.progress import ask_user

logger = logging.getLogger(__name__)

# Hard page-visit budgets per site_depth level.
# Counts browse_page + extract_css calls.
PAGE_BUDGET: dict[int, int] = {
    0: 10,   # Homepages only — target + ~5 competitors
    1: 25,   # Homepage + a few top-level pages each
    2: 50,   # Two clicks deep
}
DEFAULT_PAGE_BUDGET = 25

# Claude tool definitions
TOOLS: list[dict[str, Any]] = [
    {
        "name": "browse_page",
        "description": (
            "Fetch a page and return its structured text content: headings, "
            "navigation, main text, interactive elements, and semantic landmarks. "
            "Use this for content, feature, and UX pattern analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to browse.",
                }
            },
            "required": ["url"],
        },
    },
    {
        "name": "discover_links",
        "description": (
            "Discover internal navigation links on a page. Returns a list of "
            "{url, text} objects. Use this to find key pages to explore within "
            "the configured site_depth."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to discover links on.",
                }
            },
            "required": ["url"],
        },
    },
    {
        "name": "extract_css",
        "description": "Extract CSS custom properties, fonts, and colors from a page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to extract CSS from.",
                }
            },
            "required": ["url"],
        },
    },
    {
        "name": "ask_user",
        "description": "Ask the user a question and get their text response. Use this to validate competitor choices or clarify requirements.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user.",
                }
            },
            "required": ["question"],
        },
    },
]


def make_tool_handler(browser: BrowserManager, *, site_depth: int = 1):
    """Create an async tool handler bound to a BrowserManager instance.

    Enforces a hard page-visit budget based on ``site_depth`` so the model
    cannot burn unlimited tokens browsing pages.
    """
    budget = PAGE_BUDGET.get(site_depth, DEFAULT_PAGE_BUDGET)
    visits: list[str] = []  # URLs visited (for logging / dedup info)

    def _budget_check(url: str, tool_name: str) -> str | None:
        """Return an error string if the budget is exhausted, else None."""
        if len(visits) >= budget:
            remaining_msg = (
                f"Page budget exhausted ({budget} pages for site_depth={site_depth}). "
                f"Please produce your output with the data you have. "
                f"Visited so far: {len(visits)} pages."
            )
            logger.warning("Budget exhausted — rejecting %s(%s)", tool_name, url)
            return remaining_msg
        return None

    def _record_visit(url: str) -> None:
        visits.append(url)
        logger.info("Page visit %d/%d: %s", len(visits), budget, url)

    async def handle_tool(name: str, input: dict[str, Any]) -> str | list[str]:
        match name:
            case "browse_page":
                err = _budget_check(input["url"], name)
                if err:
                    return err
                try:
                    _record_visit(input["url"])
                    return await browser.get_page_text(input["url"])
                except Exception as exc:
                    return f"Error browsing {input['url']}: {exc}"
            case "discover_links":
                # discover_links is cheap (just link extraction) — don't count it
                try:
                    links = await browser.discover_links(input["url"])
                    remaining = budget - len(visits)
                    header = f"[{remaining} page visits remaining in budget]\n\n"
                    return header + json.dumps(links, indent=2)
                except Exception as exc:
                    return f"Error discovering links on {input['url']}: {exc}"
            case "extract_css":
                err = _budget_check(input["url"], name)
                if err:
                    return err
                try:
                    _record_visit(input["url"])
                    return await browser.extract_css(input["url"])
                except Exception as exc:
                    return f"Error extracting CSS from {input['url']}: {exc}"
            case "ask_user":
                return await ask_user(input["question"])
            case _:
                return f"Unknown tool: {name}"

    return handle_tool
