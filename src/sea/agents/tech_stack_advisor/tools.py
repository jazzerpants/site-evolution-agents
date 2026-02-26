"""Tool definitions and handler for the 4G Tech Stack Advisor agent."""

from __future__ import annotations

import json
from typing import Any

from sea.shared.codebase_reader import CodebaseReader

TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": (
            "Read a file from the codebase. Use this to inspect package manifests "
            "(package.json, pyproject.toml, requirements.txt), config files "
            "(next.config.js, vite.config.ts, webpack.config.js), and key source "
            "files to understand the current tech stack and architecture."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from the codebase root.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_code",
        "description": (
            "Search the codebase using a regex pattern. Returns matching lines with "
            "file paths and line numbers. Useful for identifying existing patterns, "
            "imports, and dependency usage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for.",
                }
            },
            "required": ["pattern"],
        },
    },
]


def make_tool_handler(reader: CodebaseReader):
    """Create an async tool handler bound to a CodebaseReader instance."""

    async def handle_tool(name: str, input: dict[str, Any]) -> str:
        match name:
            case "read_file":
                try:
                    return reader.read_file(input["path"])
                except Exception as exc:
                    return f"Error reading {input['path']}: {exc}"
            case "search_code":
                try:
                    results = reader.search_code(input["pattern"])
                    if not results:
                        return "No matches found."
                    return json.dumps(results, indent=2)
                except Exception as exc:
                    return f"Error searching for '{input['pattern']}': {exc}"
            case _:
                return f"Unknown tool: {name}"

    return handle_tool
