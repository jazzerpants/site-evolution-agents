"""Async OpenAI API wrapper with agentic tool-use loop.

Despite the filename, this now targets the OpenAI API. The interface
is unchanged so all agents work without modification.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Any, Callable, Awaitable

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

# Model all agents use
MODEL = "gpt-4o"
MAX_TOKENS = 16_384

# Retry settings for rate-limit (429) errors
_RATE_LIMIT_MAX_RETRIES = 8
_RATE_LIMIT_BASE_DELAY = 5  # seconds — minimum floor for exponential backoff


def _parse_retry_after(exc: RateLimitError) -> float | None:
    """Extract the suggested retry delay from an OpenAI rate limit error.

    Checks the ``Retry-After`` header first, then falls back to parsing
    the "Please try again in Xs / Xms" substring from the error message.
    Returns seconds as a float, or None if not found.
    """
    try:
        headers = exc.response.headers  # type: ignore[union-attr]
        if retry_after := headers.get("retry-after"):
            return float(retry_after)
    except (AttributeError, TypeError, ValueError):
        pass

    m = re.search(r"try again in (\d+(?:\.\d+)?)\s*(ms|s)\b", str(exc), re.IGNORECASE)
    if m:
        value = float(m.group(1))
        return value / 1000 if m.group(2).lower() == "ms" else value

    return None


ToolHandler = Callable[[str, dict[str, Any]], Awaitable["str | list[str]"]]
"""Signature: async (tool_name, tool_input) -> str or list of base64 image tiles."""

ProgressCallback = Callable[[str], None]
"""Called with a short status message on each loop iteration."""

TokensCallback = Callable[[int, int], None]
"""Called with (input_tokens, output_tokens) when a completion finishes."""


def _claude_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Claude-format tool definitions to OpenAI function-calling format.

    Claude:  {"name": "...", "description": "...", "input_schema": {...}}
    OpenAI:  {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
    """
    openai_tools = []
    for tool in tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return openai_tools


class ClaudeClient:
    """Thin async wrapper around the OpenAI SDK.

    Provides two methods:
    - ``run_agent_loop`` — sends a message, executes tool calls, feeds
      results back, and repeats until the model stops issuing tool calls.
    - ``simple_completion`` — single request/response with no tools.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._client = AsyncOpenAI(api_key=api_key)

    async def _call_with_retry(self, **kwargs: Any) -> Any:
        """Call chat.completions.create with exponential backoff on 429 errors.

        Waits at least as long as OpenAI's suggested retry-after time (parsed
        from the error message or header), uses exponential backoff as a floor,
        and adds ±25% jitter so parallel agents don't slam the API in sync.

        Fails immediately if the error indicates the request itself exceeds
        the token limit (retrying won't help — the payload must shrink).
        """
        for attempt in range(_RATE_LIMIT_MAX_RETRIES):
            try:
                return await self._client.chat.completions.create(**kwargs)
            except RateLimitError as exc:
                msg = str(exc).lower()
                # "Request too large" / "context_length_exceeded" means the
                # payload itself is too big — retrying won't help.
                if "request too large" in msg or "context_length_exceeded" in msg:
                    logger.error(
                        "Request exceeds token limit (not retryable): %s", exc,
                    )
                    raise
                if attempt == _RATE_LIMIT_MAX_RETRIES - 1:
                    raise

                # Use OpenAI's suggested wait time when available; fall back to
                # exponential backoff.  Add ±25% jitter so concurrent agents
                # (e.g. 4A + 4B) don't retry in lockstep.
                backoff = _RATE_LIMIT_BASE_DELAY * (2 ** attempt)
                suggested = _parse_retry_after(exc)
                base_delay = max(suggested or 0.0, backoff)
                jitter = random.uniform(-0.25 * base_delay, 0.25 * base_delay)
                delay = max(1.0, base_delay + jitter)

                logger.warning(
                    "Rate limited (429), retrying in %.1fs (attempt %d/%d, "
                    "suggested=%.1fs, backoff=%ds): %s",
                    delay, attempt + 1, _RATE_LIMIT_MAX_RETRIES,
                    suggested or 0.0, backoff, exc,
                )
                await asyncio.sleep(delay)
            except (APIConnectionError, APITimeoutError) as exc:
                if attempt == _RATE_LIMIT_MAX_RETRIES - 1:
                    raise
                # Transient network / TLS errors — short exponential backoff,
                # capped at ~40 s, with ±25% jitter.
                backoff = _RATE_LIMIT_BASE_DELAY * (2 ** min(attempt, 3))
                jitter = random.uniform(-0.25 * backoff, 0.25 * backoff)
                delay = max(2.0, backoff + jitter)
                logger.warning(
                    "Connection error, retrying in %.1fs (attempt %d/%d): %s",
                    delay, attempt + 1, _RATE_LIMIT_MAX_RETRIES, exc,
                )
                await asyncio.sleep(delay)

    # ------------------------------------------------------------------
    # Agentic tool loop
    # ------------------------------------------------------------------

    async def run_agent_loop(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_handler: ToolHandler,
        max_iterations: int = 30,
        on_progress: ProgressCallback | None = None,
        on_tokens: TokensCallback | None = None,
    ) -> str:
        """Run the tool-use loop until the model produces a final text response.

        Returns the final assistant text (expected to be JSON for most agents).
        """
        # Convert Claude tool format to OpenAI format
        openai_tools = _claude_tools_to_openai(tools) if tools else []

        # Build OpenAI messages list with system message
        oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for msg in messages:
            oai_messages.append(msg)

        _max_nudges = 2  # times to nudge model back after non-JSON text
        _nudge_count = 0
        _total_input_tokens = 0
        _total_output_tokens = 0

        for iteration in range(1, max_iterations + 1):
            if on_progress:
                on_progress(f"Thinking… (step {iteration})")

            kwargs: dict[str, Any] = {
                "model": MODEL,
                "max_tokens": MAX_TOKENS,
                "messages": oai_messages,
            }
            if openai_tools:
                kwargs["tools"] = openai_tools
            else:
                # Only enforce JSON mode when no tools are available,
                # i.e. the model must produce its final text response.
                # During tool-use iterations, JSON mode conflicts with
                # the model's ability to decide between tool calls and text.
                kwargs["response_format"] = {"type": "json_object"}

            response = await self._call_with_retry(**kwargs)
            usage = getattr(response, "usage", None)
            if usage:
                _total_input_tokens += getattr(usage, "prompt_tokens", 0)
                _total_output_tokens += getattr(usage, "completion_tokens", 0)
            choice = response.choices[0]
            message = choice.message

            # Check if the model wants to use tools
            if not message.tool_calls:
                content = message.content or ""

                # If tools are available but the model responded with plain
                # text (not JSON), it's likely "thinking aloud" mid-analysis
                # (e.g. after an ask_user result).  Nudge it back into the
                # tool-use loop.  Limited to _max_nudges to avoid loops;
                # after that, fall through to _parse_with_retry.
                if (
                    openai_tools
                    and content
                    and not content.lstrip().startswith("{")
                    and _nudge_count < _max_nudges
                ):
                    _nudge_count += 1
                    logger.info(
                        "Model responded with non-JSON text at step %d, "
                        "nudging back to tool use (nudge %d/%d, %d chars)",
                        iteration,
                        _nudge_count,
                        _max_nudges,
                        len(content),
                    )
                    oai_messages.append({"role": "assistant", "content": content})
                    oai_messages.append({
                        "role": "user",
                        "content": (
                            "Continue your analysis using the available tools. "
                            "When you have completed all required steps, respond "
                            "with your final JSON output."
                        ),
                    })
                    continue

                if on_tokens:
                    on_tokens(_total_input_tokens, _total_output_tokens)
                return content

            # Append assistant message (with tool_calls) to history
            oai_messages.append(message.model_dump())

            # Execute all tool calls for this turn concurrently, then process
            # results in order.  Image tiles (list[str]) can't go in tool
            # messages — OpenAI only allows image_url in user messages.  So we
            # return a text summary as the tool result and queue the images in
            # a user message that gets flushed after all tool results.
            async def _run_tool(tc: Any) -> tuple[Any, str, dict, "str | list[str]"]:
                fn = tc.function
                t_name = fn.name
                try:
                    t_input = json.loads(fn.arguments)
                except json.JSONDecodeError:
                    t_input = {}
                logger.info("Tool call: %s(%s)", t_name, fn.arguments[:200])
                if on_progress:
                    on_progress(f"Running tool: {t_name}")
                try:
                    t_result = await tool_handler(t_name, t_input)
                except Exception as exc:
                    logger.warning("Tool %s failed: %s", t_name, exc)
                    t_result = f"Error: {exc}"
                return tc, t_name, t_input, t_result

            tool_results = await asyncio.gather(
                *(_run_tool(tc) for tc in message.tool_calls)
            )

            _pending_image_messages: list[dict[str, Any]] = []
            for tool_call, tool_name, tool_input, result in tool_results:
                if isinstance(result, list):
                    # Image tiles — send first few to OpenAI at detail=low
                    # (85 tokens each) for visual comparison.  All tiles are
                    # stored in browser.captured_screenshots for the dashboard.
                    max_tiles_for_model = 2  # above-the-fold is enough for the model
                    tiles_for_model = result[:max_tiles_for_model]
                    total = len(result)
                    url_hint = tool_input.get("url", "unknown page")

                    oai_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": (
                            f"Full-page screenshot of {url_hint} captured "
                            f"({total} viewport-height sections, showing "
                            f"top {len(tiles_for_model)} to model). "
                            f"All {total} sections saved for the report dashboard."
                        ),
                    })
                    image_parts: list[dict[str, Any]] = [{
                        "type": "text",
                        "text": (
                            f"Screenshot of {url_hint} — top "
                            f"{len(tiles_for_model)} of {total} sections:"
                        ),
                    }]
                    for i, tile_b64 in enumerate(tiles_for_model):
                        image_parts.append({
                            "type": "text",
                            "text": f"[Section {i+1}/{total}, y={i*800}px]",
                        })
                        image_parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{tile_b64}",
                                "detail": "low",
                            },
                        })
                    _pending_image_messages.append({
                        "role": "user",
                        "content": image_parts,
                    })
                else:
                    oai_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })

            # Flush queued image messages (must come after all tool results)
            oai_messages.extend(_pending_image_messages)

        raise RuntimeError(f"Agent loop did not complete within {max_iterations} iterations")

    # ------------------------------------------------------------------
    # Simple (non-agentic) completion
    # ------------------------------------------------------------------

    async def simple_completion(
        self,
        *,
        system: str,
        user_message: str,
        json_mode: bool = True,
        on_tokens: TokensCallback | None = None,
    ) -> str:
        """Single request/response with no tools.

        When ``json_mode`` is True (default), the OpenAI API guarantees
        the response is valid JSON.
        """
        kwargs: dict[str, Any] = {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._call_with_retry(**kwargs)
        usage = getattr(response, "usage", None)
        if on_tokens and usage:
            on_tokens(getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0))
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # Vision completion (multipart content with images)
    # ------------------------------------------------------------------

    async def vision_completion(
        self,
        *,
        system: str,
        content: list[dict[str, Any]],
        json_mode: bool = True,
        on_tokens: TokensCallback | None = None,
    ) -> str:
        """Single request/response with multipart content (text + images).

        ``content`` is a list of OpenAI content parts, e.g.:
            [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {...}}]

        When ``json_mode`` is True (default), the OpenAI API guarantees
        the response is valid JSON.
        """
        kwargs: dict[str, Any] = {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._call_with_retry(**kwargs)
        usage = getattr(response, "usage", None)
        if on_tokens and usage:
            on_tokens(getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0))
        return response.choices[0].message.content or ""


# ======================================================================
# Dry-run mock client — zero API calls
# ======================================================================

# Canned JSON responses keyed by agent name prefix found in system prompt
_DRY_RUN_TOOL_SCRIPTS: dict[str, list[tuple[str, dict]]] = {
    "4A": [
        ("ask_user", {"question": "What industry or category does this site serve?"}),
        ("ask_user", {"question": "Who is the primary target audience?"}),
        ("ask_user", {"question": "Do you have specific competitor sites in mind?"}),
    ],
    "4B": [
        ("get_tree", {}),
        ("read_manifest", {}),
    ],
    "4D": [
        ("read_file", {"path": "package.json"}),
    ],
    "4E": [],
}

_DRY_RUN_JSON: dict[str, str] = {
    "4A": json.dumps({
        "competitors": [
            {
                "name": "Example Competitor",
                "url": "https://example.com",
                "strengths": ["Clean design"],
                "weaknesses": ["Slow load"],
                "features": [{"name": "Dark mode", "description": "Theme toggle", "category": "UX"}],
            }
        ],
        "feature_matrix": [{"feature": "Dark mode", "target_has": False, "competitors_with": ["Example Competitor"]}],
        "ux_gaps": [{"gap": "No dark mode", "severity": "medium", "competitors_solving": ["Example Competitor"]}],
        "design_patterns": [{"pattern": "Card layout", "used_by": ["Example Competitor"], "description": "Grid cards"}],
    }),
    "4B": json.dumps({
        "tech_stack": [{"name": "Next.js", "category": "Framework", "version": "16.0.8", "ux_pros": ["SSR"], "ux_cons": ["Complex config"]}],
        "architecture": {"routing_pattern": "app router", "data_flow": "server components", "component_tree_summary": "App > Layout > Pages", "mermaid_diagram": "graph TD; A-->B;"},
        "components": [{"name": "Nav", "file_path": "src/components/Nav.tsx", "description": "Main navigation", "has_tests": False}],
        "tech_debt": [{"description": "No tests", "severity": "medium", "location": "src/", "suggestion": "Add Jest"}],
        "extensibility": {"overall_score": "good", "strengths": ["Modular"], "weaknesses": ["No test infra"], "notes": ""},
        "design_system": {"has_design_system": False, "semantic_tokens": [], "theming_support": "none", "animation_patterns": [], "component_library": "none"},
        "bundle_notes": "No tree-shaking issues detected",
        "summary": "Modern Next.js 16 app with room for improvement in testing.",
    }),
    "4C_pass1": json.dumps({
        "recommendations": [
            {"id": "REC-001", "title": "Add dark mode", "category": "quick-win", "estimated_complexity": "low",
             "description": "Implement theme toggle", "rationale": "Improves UX",
             "scores": {"user_value": 8, "novelty": 5, "feasibility": 9}, "rank": 1},
        ],
        "quick_wins": ["REC-001"],
        "long_term": [],
        "summary": "Top recommendation: add dark mode.",
    }),
    "4C_pass2": json.dumps({
        "recommendations": [
            {"id": "REC-001", "title": "Add dark mode", "category": "quick-win", "estimated_complexity": "low",
             "description": "Implement theme toggle", "rationale": "Improves UX",
             "scores": {"user_value": 8, "novelty": 5, "feasibility": 9}, "rank": 1},
        ],
        "promoted": [],
        "demoted": [],
        "quick_wins": ["REC-001"],
        "long_term": [],
        "summary": "Rankings unchanged after feasibility review.",
    }),
    "4D": json.dumps({
        "assessments": [
            {"recommendation_id": "REC-001", "rating": "easy", "cost_estimate": "small",
             "developer_days": "2 days", "risk": "low", "notes": "Straightforward CSS variable approach"},
        ],
        "summary": "All recommendations are feasible.",
    }),
    "4E": json.dumps({
        "accessibility": {"wcag_level": "AA", "issues": [], "keyboard_navigation": "good", "screen_reader_notes": "Needs ARIA labels", "aria_usage": "minimal"},
        "performance": {"metrics": [{"name": "LCP", "value": "1.2s", "rating": "good"}], "bundle_analysis": "Clean", "image_optimization": "Good", "caching_strategy": "Default", "critical_rendering_path": "OK"},
        "priority_issues": [{"description": "Add ARIA labels to nav", "category": "accessibility", "impact": "medium", "effort_to_fix": "low"}],
        "summary": "Good baseline quality with minor accessibility gaps.",
    }),
    "4F": json.dumps({
        "layout": {"visual_hierarchy": "Good use of headings", "whitespace_usage": "Adequate spacing", "grid_consistency": "Consistent grid", "responsive_notes": "Mobile-friendly layout"},
        "typography": {"readability": "Clear font choices", "hierarchy": "Distinct heading levels", "consistency": "Consistent across pages"},
        "color": {"palette_coherence": "Cohesive palette", "contrast_notes": "Good contrast ratios", "brand_consistency": "Consistent brand colors", "dark_mode_notes": "No dark mode detected"},
        "navigation": {"clarity": "Clear navigation structure", "information_architecture": "Logical organization", "mobile_notes": "Hamburger menu on mobile"},
        "issues": [{"area": "color", "description": "No dark mode support", "severity": "minor", "recommendation": "Add CSS custom properties for theming", "competitors_doing_better": ["Example Competitor"]}],
        "strengths": ["Clean, modern layout", "Good typography hierarchy"],
        "overall_impression": "Solid visual design with room for improvement in theming.",
        "summary": "The site has a clean, modern design. Key opportunity: add dark mode support.",
    }),
    "synthesis": "# Executive Summary\n\nThe site is a modern Next.js application. Top recommendation: add dark mode (REC-001).",
}


class DryRunClient:
    """Drop-in replacement for ClaudeClient that makes zero API calls.

    Executes a short scripted sequence of tool calls per agent so the full
    pipeline runs — including ask_user prompts — then returns canned JSON.
    """

    async def run_agent_loop(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_handler: ToolHandler,
        max_iterations: int = 30,
        on_progress: ProgressCallback | None = None,
        on_tokens: TokensCallback | None = None,
    ) -> str:
        agent_key = self._detect_agent(system)
        script = _DRY_RUN_TOOL_SCRIPTS.get(agent_key, [])

        # Execute scripted tool calls
        for i, (tool_name, tool_input) in enumerate(script, 1):
            if on_progress:
                on_progress(f"Iteration {i}/{max_iterations}")
            logger.info("[dry-run] Tool call: %s(%s)", tool_name, json.dumps(tool_input)[:200])
            if on_progress:
                on_progress(f"Running tool: {tool_name}")
            try:
                await tool_handler(tool_name, tool_input)
            except Exception as exc:
                logger.warning("[dry-run] Tool %s failed: %s", tool_name, exc)

        # Return canned JSON
        if on_progress:
            on_progress(f"Iteration {len(script) + 1}/{max_iterations}")
        return _DRY_RUN_JSON.get(agent_key, "{}")

    async def simple_completion(
        self,
        *,
        system: str,
        user_message: str,
        json_mode: bool = True,
        on_tokens: TokensCallback | None = None,
    ) -> str:
        key = self._detect_agent(system)
        # 4C uses simple_completion for both passes — distinguish by input
        if key == "4C":
            if "pass1_recommendations" in user_message:
                key = "4C_pass2"
            else:
                key = "4C_pass1"
        return _DRY_RUN_JSON.get(key, _DRY_RUN_JSON["synthesis"])

    async def vision_completion(
        self,
        *,
        system: str,
        content: list[dict[str, Any]],
        json_mode: bool = True,
        on_tokens: TokensCallback | None = None,
    ) -> str:
        key = self._detect_agent(system)
        return _DRY_RUN_JSON.get(key, "{}")

    @staticmethod
    def _detect_agent(system: str) -> str:
        """Guess agent key from the system prompt.

        Order matters — check agents whose prompts reference other agents
        (4C mentions 4A/4B) before the agents they reference.
        """
        if "Agent 4C" in system or "Feature Recommender" in system:
            return "4C"
        if "Agent 4D" in system or "Feasibility" in system:
            return "4D"
        if "Agent 4E" in system or "Quality Audit" in system:
            return "4E"
        if "Agent 4F" in system or "UX Design" in system:
            return "4F"
        if "Agent 4A" in system or "Comparative Research" in system:
            return "4A"
        if "Agent 4B" in system or "Code Analysis" in system:
            return "4B"
        return "synthesis"
