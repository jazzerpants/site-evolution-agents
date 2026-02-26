"""Tool definitions and handler for the 4D Tech Feasibility agent."""

from __future__ import annotations

import json
from typing import Any

from sea.shared.codebase_reader import CodebaseReader

TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read the contents of a file in the codebase.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file from the codebase root.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_code",
        "description": "Search across all files in the codebase for a regex pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for (case-insensitive).",
                }
            },
            "required": ["pattern"],
        },
    },
]


def make_tool_handler(reader: CodebaseReader):
    """Create an async tool handler bound to a CodebaseReader."""

    async def handle_tool(name: str, input: dict[str, Any]) -> str:
        match name:
            case "read_file":
                return reader.read_file(input["path"])
            case "search_code":
                results = reader.search_code(input["pattern"])
                if not results:
                    return "No matches found."
                return json.dumps(results, indent=2)
            case _:
                return f"Unknown tool: {name}"

    return handle_tool
