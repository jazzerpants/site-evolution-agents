"""Tool definitions and handler for the 4E Quality Audit agent."""

from __future__ import annotations

import json
from typing import Any

from sea.shared.browser import BrowserManager
from sea.shared.codebase_reader import CodebaseReader

TOOLS: list[dict[str, Any]] = [
    {
        "name": "run_axe",
        "description": "Run axe-core accessibility audit on a URL. Returns violation details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to audit."}
            },
            "required": ["url"],
        },
    },
    {
        "name": "measure_vitals",
        "description": "Measure performance metrics (LCP, FCP, load time, etc.) for a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to measure."}
            },
            "required": ["url"],
        },
    },
    {
        "name": "screenshot",
        "description": "Take a full-page screenshot of a URL. Returns viewport-height sections of the full page as images for visual analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to screenshot."}
            },
            "required": ["url"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the codebase (if available).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from codebase root."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_code",
        "description": "Search the codebase for a regex pattern (if available).",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for."}
            },
            "required": ["pattern"],
        },
    },
]


def make_tool_handler(browser: BrowserManager, reader: CodebaseReader | None = None):
    """Create an async tool handler for the quality audit agent."""

    async def handle_tool(name: str, input: dict[str, Any]) -> str | list[str]:
        match name:
            case "run_axe":
                try:
                    return await browser.run_axe(input["url"])
                except Exception as exc:
                    return f"Error running axe audit: {exc}"
            case "measure_vitals":
                try:
                    return await browser.measure_vitals(input["url"])
                except Exception as exc:
                    return f"Error measuring vitals: {exc}"
            case "screenshot":
                try:
                    return await browser.take_screenshot(input["url"])
                except Exception as exc:
                    return f"Error taking screenshot: {exc}"
            case "read_file":
                if reader is None:
                    return "Codebase not available for this analysis."
                return reader.read_file(input["path"])
            case "search_code":
                if reader is None:
                    return "Codebase not available for this analysis."
                results = reader.search_code(input["pattern"])
                if not results:
                    return "No matches found."
                return json.dumps(results, indent=2)
            case _:
                return f"Unknown tool: {name}"

    return handle_tool
