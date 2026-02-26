"""Tests for the BaseAgent ABC contract."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from sea.agents.base import BaseAgent, extract_json
from sea.shared.claude_client import ClaudeClient


class SampleOutput(BaseModel):
    result: str
    count: int = 0


class SampleAgent(BaseAgent):
    """Concrete test implementation of BaseAgent."""

    @property
    def name(self) -> str:
        return "Sample Agent"

    def get_system_prompt(self) -> str:
        return "You are a test agent."

    def get_tools(self) -> list[dict[str, Any]]:
        return [{"name": "test_tool", "description": "test", "input_schema": {"type": "object", "properties": {}}}]

    def get_tool_handler(self):
        async def handler(name: str, input: dict) -> str:
            return "tool result"
        return handler

    def parse_output(self, raw_text: str) -> SampleOutput:
        data = extract_json(raw_text)
        return SampleOutput(**data)


def _mock_openai_response(content: str) -> SimpleNamespace:
    """Build a fake OpenAI response with the given text content."""
    message = SimpleNamespace(content=content, tool_calls=None)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


class TestBaseAgent:
    @pytest.mark.asyncio
    async def test_run_returns_parsed_output(self) -> None:
        client = ClaudeClient.__new__(ClaudeClient)
        client._client = AsyncMock()

        client._client.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response('{"result": "success", "count": 42}')
        )

        agent = SampleAgent(client)
        output = await agent.run("test input")

        assert isinstance(output, SampleOutput)
        assert output.result == "success"
        assert output.count == 42

    def test_name(self) -> None:
        client = ClaudeClient.__new__(ClaudeClient)
        agent = SampleAgent(client)
        assert agent.name == "Sample Agent"


class TestExtractJson:
    def test_nested_json(self) -> None:
        text = json.dumps({"a": {"b": [1, 2, 3]}})
        data = extract_json(text)
        assert data["a"]["b"] == [1, 2, 3]

    def test_json_with_whitespace(self) -> None:
        text = "  \n  {\"key\": \"value\"}  \n  "
        data = extract_json(text)
        assert data["key"] == "value"

    def test_invalid_json_raises(self) -> None:
        with pytest.raises((json.JSONDecodeError, ValueError)):
            extract_json("not json at all")


class TestExtractJsonMalformedResponses:
    """Test extract_json against realistic malformed model responses."""

    def test_markdown_heading_analysis(self) -> None:
        """Model returns a full markdown report with headings and bullets."""
        text = (
            "# Code Analysis\n\n"
            "## Tech Stack\n"
            "- **Next.js** (16.0.8) — SSR framework\n"
            "- **React** (19.2.1) — UI library\n\n"
            "## Summary\n"
            "The codebase is modern and well-structured.\n"
        )
        with pytest.raises(ValueError, match="Could not extract JSON"):
            extract_json(text)

    def test_markdown_with_json_inside(self) -> None:
        """Model wraps valid JSON in explanation text."""
        text = (
            "Here is my analysis in the requested format:\n\n"
            '{"result": "success", "count": 7}\n\n'
            "Let me know if you need anything else!"
        )
        data = extract_json(text)
        assert data["result"] == "success"
        assert data["count"] == 7

    def test_json_in_markdown_code_fence(self) -> None:
        """Model wraps JSON in ```json ... ``` fences."""
        text = (
            "Here is the output:\n\n"
            "```json\n"
            '{"result": "found", "count": 3}\n'
            "```\n\n"
            "This represents the analysis."
        )
        data = extract_json(text)
        assert data["result"] == "found"
        assert data["count"] == 3

    def test_json_in_plain_code_fence(self) -> None:
        """Model wraps JSON in ``` ... ``` fences without the json tag."""
        text = (
            "Output:\n\n"
            "```\n"
            '{"result": "ok", "count": 0}\n'
            "```"
        )
        data = extract_json(text)
        assert data["result"] == "ok"

    def test_pure_markdown_no_json_at_all(self) -> None:
        """Model returns a fully narrative response."""
        text = (
            "Based on my analysis of the codebase, I found that the application "
            "uses a modern stack with Next.js and React. The architecture follows "
            "standard patterns with server components and app router.\n\n"
            "I recommend focusing on accessibility improvements first."
        )
        with pytest.raises(ValueError, match="Could not extract JSON"):
            extract_json(text)

    def test_markdown_table_response(self) -> None:
        """Model returns a markdown table instead of JSON."""
        text = (
            "| Technology | Version | Notes |\n"
            "|-----------|---------|-------|\n"
            "| Next.js | 16.0.8 | SSR framework |\n"
            "| React | 19.2.1 | UI library |\n"
        )
        with pytest.raises(ValueError, match="Could not extract JSON"):
            extract_json(text)

    def test_truncated_json(self) -> None:
        """Model returns JSON that was cut off mid-stream."""
        text = '{"result": "success", "count": 42, "items": ['
        with pytest.raises((ValueError, json.JSONDecodeError)):
            extract_json(text)

    def test_json_with_trailing_markdown(self) -> None:
        """Model appends commentary after valid JSON."""
        text = (
            '{"result": "done", "count": 5}\n\n'
            "Note: I focused on the most critical components."
        )
        data = extract_json(text)
        assert data["result"] == "done"

    def test_multiple_json_blocks(self) -> None:
        """Model returns multiple JSON objects — extract_json picks the first."""
        text = (
            "Step 1 result:\n"
            '{"result": "first", "count": 1}\n\n'
            "Step 2 result:\n"
            '{"result": "second", "count": 2}\n'
        )
        data = extract_json(text)
        # Should get the outermost { to } span
        assert "result" in data

    def test_error_message_includes_preview(self) -> None:
        """The ValueError includes the first 300 chars for debugging."""
        long_text = "This is not JSON. " * 50
        with pytest.raises(ValueError, match="First 300 chars"):
            extract_json(long_text)


class TestRetryOnMalformedResponse:
    """Test that _parse_with_retry sends a follow-up when the first response is not JSON."""

    @pytest.mark.asyncio
    async def test_retry_on_markdown_response(self) -> None:
        """First call returns markdown, retry returns valid JSON."""
        client = ClaudeClient.__new__(ClaudeClient)
        client._client = AsyncMock()

        markdown_response = _mock_openai_response(
            "# Analysis\n\nThe codebase uses Next.js and React."
        )
        json_response = _mock_openai_response(
            '{"result": "success", "count": 10}'
        )

        # First call returns markdown (the agentic loop), second returns JSON (the retry)
        client._client.chat.completions.create = AsyncMock(
            side_effect=[markdown_response, json_response]
        )

        agent = SampleAgent(client)
        output = await agent.run("analyze this")

        assert isinstance(output, SampleOutput)
        assert output.result == "success"
        assert output.count == 10
        # Should have been called twice: original + retry
        assert client._client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_nudge_message_appended(self) -> None:
        """When the model returns non-JSON text mid-analysis, it gets nudged back."""
        client = ClaudeClient.__new__(ClaudeClient)
        client._client = AsyncMock()

        bad_text = "Here is a markdown summary of the code."
        markdown_response = _mock_openai_response(bad_text)
        json_response = _mock_openai_response('{"result": "ok", "count": 0}')

        calls = []

        async def capture_calls(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return markdown_response
            return json_response

        client._client.chat.completions.create = AsyncMock(side_effect=capture_calls)

        agent = SampleAgent(client)
        await agent.run("test")

        # The nudge should have appended the bad text as assistant + a
        # "continue your analysis" user message
        nudge_messages = calls[1]["messages"]
        assert any(m.get("role") == "assistant" and bad_text in m.get("content", "") for m in nudge_messages)
        assert any("continue" in m.get("content", "").lower() for m in nudge_messages if m.get("role") == "user")

    @pytest.mark.asyncio
    async def test_retry_fails_raises(self) -> None:
        """If nudges and retry both fail, the error propagates."""
        client = ClaudeClient.__new__(ClaudeClient)
        client._client = AsyncMock()

        # Need enough bad responses: 2 nudges in run_agent_loop + 1 return
        # from run_agent_loop + 1 for the _parse_with_retry re-format call
        bad = _mock_openai_response("Still not JSON.")

        client._client.chat.completions.create = AsyncMock(
            side_effect=[bad, bad, bad, bad]
        )

        agent = SampleAgent(client)
        with pytest.raises(ValueError, match="Could not extract JSON"):
            await agent.run("test")

    @pytest.mark.asyncio
    async def test_no_retry_when_json_is_valid(self) -> None:
        """No retry call when the first response is valid JSON."""
        client = ClaudeClient.__new__(ClaudeClient)
        client._client = AsyncMock()

        client._client.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response('{"result": "good", "count": 1}')
        )

        agent = SampleAgent(client)
        output = await agent.run("test")

        assert output.result == "good"
        assert client._client.chat.completions.create.call_count == 1
