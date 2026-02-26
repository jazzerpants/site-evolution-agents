"""Tests for the ClaudeClient — mock the OpenAI SDK to test the agent loop."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sea.shared.claude_client import ClaudeClient, _claude_tools_to_openai


def _make_text_response(text: str):
    """Create a mock OpenAI response with text only (no tool calls)."""
    message = SimpleNamespace(content=text, tool_calls=None)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _make_tool_response(tool_name: str, arguments: str, tool_id: str = "call_abc123"):
    """Create a mock OpenAI response with a tool call."""
    fn = SimpleNamespace(name=tool_name, arguments=arguments)
    tool_call = SimpleNamespace(id=tool_id, function=fn, type="function")
    # model_dump for when it gets appended to messages
    tool_call.model_dump = lambda: {
        "id": tool_id,
        "type": "function",
        "function": {"name": tool_name, "arguments": arguments},
    }
    message = SimpleNamespace(content=None, tool_calls=[tool_call])
    message.model_dump = lambda: {
        "role": "assistant",
        "content": None,
        "tool_calls": [tool_call.model_dump()],
    }
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


class TestToolConversion:
    def test_claude_to_openai_format(self) -> None:
        claude_tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ]
        openai_tools = _claude_tools_to_openai(claude_tools)
        assert len(openai_tools) == 1
        assert openai_tools[0]["type"] == "function"
        assert openai_tools[0]["function"]["name"] == "read_file"
        assert openai_tools[0]["function"]["parameters"]["required"] == ["path"]


class TestSimpleCompletion:
    @pytest.mark.asyncio
    async def test_returns_text(self) -> None:
        client = ClaudeClient.__new__(ClaudeClient)
        client._client = AsyncMock()
        client._client.chat.completions.create = AsyncMock(
            return_value=_make_text_response("Hello!")
        )

        result = await client.simple_completion(system="sys", user_message="hi")
        assert result == "Hello!"


class TestRunAgentLoop:
    @pytest.mark.asyncio
    async def test_immediate_text_response(self) -> None:
        """Model returns text on first call (no tool use)."""
        client = ClaudeClient.__new__(ClaudeClient)
        client._client = AsyncMock()
        client._client.chat.completions.create = AsyncMock(
            return_value=_make_text_response('{"result": "done"}')
        )

        result = await client.run_agent_loop(
            system="sys",
            messages=[{"role": "user", "content": "analyze"}],
            tools=[],
            tool_handler=AsyncMock(),
        )
        assert '"result"' in result

    @pytest.mark.asyncio
    async def test_tool_use_then_text(self) -> None:
        """Model uses a tool, then returns text."""
        client = ClaudeClient.__new__(ClaudeClient)
        client._client = AsyncMock()

        client._client.chat.completions.create = AsyncMock(
            side_effect=[
                _make_tool_response("read_file", '{"path": "src/index.ts"}'),
                _make_text_response('{"result": "analyzed"}'),
            ]
        )

        tool_handler = AsyncMock(return_value="file contents here")

        result = await client.run_agent_loop(
            system="sys",
            messages=[{"role": "user", "content": "analyze"}],
            tools=[{"name": "read_file", "description": "...", "input_schema": {}}],
            tool_handler=tool_handler,
        )

        assert '"result"' in result
        tool_handler.assert_called_once_with("read_file", {"path": "src/index.ts"})

    @pytest.mark.asyncio
    async def test_tool_error_is_reported(self) -> None:
        """If tool handler raises, error string is fed back."""
        client = ClaudeClient.__new__(ClaudeClient)
        client._client = AsyncMock()

        client._client.chat.completions.create = AsyncMock(
            side_effect=[
                _make_tool_response("bad_tool", "{}"),
                _make_text_response('{"handled": "error"}'),
            ]
        )

        tool_handler = AsyncMock(side_effect=RuntimeError("boom"))

        result = await client.run_agent_loop(
            system="sys",
            messages=[{"role": "user", "content": "go"}],
            tools=[{"name": "bad_tool", "description": "...", "input_schema": {}}],
            tool_handler=tool_handler,
        )
        assert '"handled"' in result

    @pytest.mark.asyncio
    async def test_max_iterations_raises(self) -> None:
        """If tool loop exceeds max iterations, raises RuntimeError."""
        client = ClaudeClient.__new__(ClaudeClient)
        client._client = AsyncMock()

        client._client.chat.completions.create = AsyncMock(
            return_value=_make_tool_response("loop_tool", "{}")
        )

        tool_handler = AsyncMock(return_value="ok")

        with pytest.raises(RuntimeError, match="did not complete"):
            await client.run_agent_loop(
                system="sys",
                messages=[{"role": "user", "content": "go"}],
                tools=[{"name": "loop_tool", "description": "...", "input_schema": {}}],
                tool_handler=tool_handler,
                max_iterations=3,
            )

    @pytest.mark.asyncio
    async def test_progress_callback(self) -> None:
        """Progress callback is called on each iteration."""
        client = ClaudeClient.__new__(ClaudeClient)
        client._client = AsyncMock()
        client._client.chat.completions.create = AsyncMock(
            return_value=_make_text_response("done")
        )

        progress_calls: list[str] = []

        await client.run_agent_loop(
            system="sys",
            messages=[{"role": "user", "content": "go"}],
            tools=[],
            tool_handler=AsyncMock(),
            on_progress=lambda msg: progress_calls.append(msg),
        )
        assert len(progress_calls) >= 1
        assert "step 1" in progress_calls[0]
