"""Tool definitions and handler for the 4B Code Analysis agent."""

from __future__ import annotations

import json
from typing import Any

from sea.shared.codebase_reader import CodebaseReader

# Claude tool definitions (JSON Schema format)
TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_dir",
        "description": "List the contents of a directory in the codebase. Returns file and directory names.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from the codebase root. Use '.' for the root directory.",
                }
            },
            "required": ["path"],
        },
    },
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
        "description": "Search across all files in the codebase for a regex pattern. Returns matching lines with file paths and line numbers.",
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
    {
        "name": "get_tree",
        "description": "Get an indented directory tree of the codebase (up to 3 levels deep).",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "read_manifest",
        "description": "Read the project manifest file (package.json, pyproject.toml, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


def make_tool_handler(reader: CodebaseReader):
    """Create an async tool handler bound to a CodebaseReader instance."""

    async def handle_tool(name: str, input: dict[str, Any]) -> str:
        match name:
            case "list_dir":
                entries = reader.list_directory(input.get("path", "."))
                return "\n".join(entries)
            case "read_file":
                return reader.read_file(input["path"])
            case "search_code":
                results = reader.search_code(input["pattern"])
                if not results:
                    return "No matches found."
                return json.dumps(results, indent=2)
            case "get_tree":
                return reader.get_tree()
            case "read_manifest":
                return reader.read_manifest()
            case _:
                return f"Unknown tool: {name}"

    return handle_tool
