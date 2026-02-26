"""Base agent ABC — defines the pattern every agent follows."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from sea.shared.claude_client import ClaudeClient, ToolHandler

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all pipeline agents.

    Subclasses implement:
    - ``name`` — human-readable agent name
    - ``get_system_prompt()`` — returns the system prompt string
    - ``get_tools()`` — returns Claude tool definitions (list of dicts)
    - ``get_tool_handler()`` — returns the async tool handler callable
    - ``parse_output(raw_text)`` — parses Claude's final text into a Pydantic model
    """

    def __init__(self, client: ClaudeClient) -> None:
        self.client = client

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for progress display."""

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""

    @abstractmethod
    def get_tools(self) -> list[dict[str, Any]]:
        """Return Claude tool definitions."""

    @abstractmethod
    def get_tool_handler(self) -> ToolHandler:
        """Return the async function that executes tool calls."""

    @abstractmethod
    def parse_output(self, raw_text: str) -> BaseModel:
        """Parse Claude's final text response into a Pydantic model."""

    async def run(
        self,
        user_message: str,
        *,
        on_progress: Any | None = None,
        on_event: Any | None = None,
    ) -> BaseModel:
        """Run the agent loop and return the parsed output model.

        1. Calls ``run_agent_loop`` with system prompt, tools, and user message
        2. Parses the final text response into the output Pydantic model
        3. If parsing fails, asks the model to re-format as JSON (one retry)
        """
        messages = [{"role": "user", "content": user_message}]

        raw = await self.client.run_agent_loop(
            system=self.get_system_prompt(),
            messages=messages,
            tools=self.get_tools(),
            tool_handler=self.get_tool_handler(),
            on_progress=on_progress,
        )

        logger.debug("Agent %s raw output:\n%s", self.name, raw[:500])
        return await self._parse_with_retry(
            raw, messages, on_progress=on_progress, on_event=on_event,
        )

    async def _parse_with_retry(
        self,
        raw: str,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        on_progress: Any | None = None,
        on_event: Any | None = None,
    ) -> BaseModel:
        """Try to parse model output as JSON; on failure ask the model to re-format.

        This is used by ``run()`` and can be called directly from custom
        ``run_*`` methods (e.g. ``run_audit``, ``run_assessment``) that
        bypass ``run()``.

        ``on_event`` is called with persistent log messages (not spinner updates).
        """
        try:
            return self.parse_output(raw)
        except (ValueError, json.JSONDecodeError, KeyError) as first_err:
            logger.warning(
                "Agent %s output was not valid JSON, requesting re-format. "
                "Error: %s",
                self.name,
                first_err,
            )

        # Ask the model to re-format its response as JSON.
        if on_progress:
            on_progress("Re-formatting output as JSON…")
        if on_event:
            on_event("[yellow]Output was not valid JSON — requesting re-format[/]")

        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": (
                "Your analysis is excellent, but I need the output as a single "
                "JSON object (no markdown, no explanation — just raw JSON) "
                "matching the schema described in your instructions. "
                "Please re-format your response now."
            ),
        })

        raw_retry = await self.client.run_agent_loop(
            system=system or self.get_system_prompt(),
            messages=messages,
            tools=[],
            tool_handler=self.get_tool_handler(),
            on_progress=on_progress,
        )

        logger.debug("Agent %s retry output:\n%s", self.name, raw_retry[:500])
        try:
            result = self.parse_output(raw_retry)
        except (ValueError, json.JSONDecodeError, KeyError) as retry_err:
            if on_event:
                on_event("[red]Re-format also failed — could not parse JSON[/]")
            raise
        if on_event:
            on_event("[green]Re-format succeeded — valid JSON on retry[/]")
        return result


def extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from text that may contain markdown fences."""
    import re

    text = text.strip()

    # 1. Try direct parse (clean JSON response)
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Might have trailing text — try raw_decode
            try:
                obj, _ = json.JSONDecoder().raw_decode(text)
                return obj
            except json.JSONDecodeError:
                pass

    # 2. Look for ```json ... ``` or ``` ... ``` fenced blocks
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())

    # 3. Find the first { and try to parse a JSON object starting there
    try:
        start = text.index("{")
        obj, _ = json.JSONDecoder().raw_decode(text, idx=start)
        return obj
    except (ValueError, json.JSONDecodeError):
        pass

    raise ValueError(
        f"Could not extract JSON from model response (length={len(text)}). "
        f"First 300 chars: {text[:300]!r}"
    )
