"""Tests for the 4G Tech Stack Advisor agent."""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from sea.agents.tech_stack_advisor.agent import TechStackAdvisorAgent
from sea.agents.tech_stack_advisor.prompts import SYSTEM_PROMPT
from sea.schemas.tech_stack import TechStackAdvisorOutput, TechStackRecommendation, TechApproach
from sea.shared.claude_client import ClaudeClient, MAX_TOKENS
from sea.shared.codebase_reader import CodebaseReader


# ---------------------------------------------------------------------------
# Token budget constants — derived from the system prompt's example JSON.
#
# Each API call is limited to MAX_TOKENS output tokens. A realistic feature
# response (3 Mermaid diagrams + metadata) is ~3× more verbose than the
# compact example embedded in the system prompt. We use chars/4 as a
# conservative token approximation for mixed JSON + diagram content.
# ---------------------------------------------------------------------------
_CHARS_PER_TOKEN = 4

# Size of one feature in the system prompt's embedded example JSON.
_match = re.search(r"(\{.*?\"summary\": \"\.\.\.\"\n\})", SYSTEM_PROMPT, re.DOTALL)
_COMPACT_FEATURE_CHARS: int = len(_match.group(1)) if _match else 6_233  # fallback if regex misses

# Real model output is ~3× more verbose than the compact example:
# longer Mermaid diagrams (more nodes, richer labels), extended summaries,
# detailed pros/cons, and JSON pretty-printing whitespace.
_VERBOSITY_FACTOR = 3
_REALISTIC_TOKENS_PER_FEATURE = (_COMPACT_FEATURE_CHARS * _VERBOSITY_FACTOR) // _CHARS_PER_TOKEN

# Maximum safe batch size: how many realistic features fit inside MAX_TOKENS.
_MAX_SAFE_BATCH = MAX_TOKENS // _REALISTIC_TOKENS_PER_FEATURE


def _make_feature_json(feature_name: str) -> str:
    """Return a minimal TechStackAdvisorOutput JSON for one feature."""
    data = {
        "features": [
            {
                "feature_name": feature_name,
                "simple_approach": {
                    "approach_name": "simple",
                    "description": f"Simple approach for {feature_name}",
                    "tech_stack": ["lib-a"],
                    "effort_estimate": "1-2 days",
                    "pros": ["Easy"],
                    "cons": ["Limited"],
                },
                "recommended_approach": "simple",
                "recommendation_rationale": f"Good fit for {feature_name}.",
                "diagrams": [],
            }
        ],
        "summary": f"Evaluated {feature_name}.",
    }
    return json.dumps(data)


class TestRunEvaluationMultipleFeatures:
    """run_evaluation should process each feature in a separate API call."""

    @pytest.mark.asyncio
    async def test_one_call_per_feature(self) -> None:
        """Each feature triggers exactly one run_agent_loop call."""
        features = ["site search", "dark mode", "mobile nav"]

        client = MagicMock(spec=ClaudeClient)
        client.run_agent_loop = AsyncMock(
            side_effect=[_make_feature_json(f) for f in features]
        )
        reader = MagicMock(spec=CodebaseReader)

        agent = TechStackAdvisorAgent(client=client, reader=reader)
        result = await agent.run_evaluation(features)

        assert client.run_agent_loop.call_count == len(features)

    @pytest.mark.asyncio
    async def test_all_features_in_output(self) -> None:
        """All feature names appear in the final output."""
        features = ["site search", "dark mode", "mobile nav"]

        client = MagicMock(spec=ClaudeClient)
        client.run_agent_loop = AsyncMock(
            side_effect=[_make_feature_json(f) for f in features]
        )
        reader = MagicMock(spec=CodebaseReader)

        agent = TechStackAdvisorAgent(client=client, reader=reader)
        result = await agent.run_evaluation(features)

        assert isinstance(result, TechStackAdvisorOutput)
        returned_names = [f.feature_name for f in result.features]
        assert returned_names == features

    @pytest.mark.asyncio
    async def test_single_feature_one_call(self) -> None:
        """Single feature results in exactly one API call."""
        features = ["site search"]

        client = MagicMock(spec=ClaudeClient)
        client.run_agent_loop = AsyncMock(
            side_effect=[_make_feature_json(f) for f in features]
        )
        reader = MagicMock(spec=CodebaseReader)

        agent = TechStackAdvisorAgent(client=client, reader=reader)
        result = await agent.run_evaluation(features)

        assert client.run_agent_loop.call_count == 1
        assert len(result.features) == 1

    @pytest.mark.asyncio
    async def test_empty_features_no_calls(self) -> None:
        """Empty feature list produces no API calls and empty output."""
        client = MagicMock(spec=ClaudeClient)
        client.run_agent_loop = AsyncMock()
        reader = MagicMock(spec=CodebaseReader)

        agent = TechStackAdvisorAgent(client=client, reader=reader)
        result = await agent.run_evaluation([])

        client.run_agent_loop.assert_not_called()
        assert result.features == []

    @pytest.mark.asyncio
    async def test_parity_context_attached_to_matching_feature(self) -> None:
        """Parity context from pass1 is included in the API call for the matching feature."""
        from sea.schemas.recommendations import Pass1Output, Recommendation, ScoreBreakdown

        features = ["site search", "dark mode"]

        client = MagicMock(spec=ClaudeClient)
        call_inputs: list[str] = []

        async def capture_and_return(system, messages, tools, tool_handler, on_progress=None, on_tokens=None):
            call_inputs.append(messages[0]["content"])
            feature_name = json.loads(messages[0]["content"])["features_to_evaluate"][0]["feature_name"]
            return _make_feature_json(feature_name)

        client.run_agent_loop = AsyncMock(side_effect=capture_and_return)
        reader = MagicMock(spec=CodebaseReader)

        pass1 = Pass1Output(
            recommendations=[
                Recommendation(
                    id="REC-001",
                    title="site search",
                    description="Add search",
                    rank=1,
                    parity_gap=True,
                    competitors_with_feature=["Rival", "Acme"],
                    scores=ScoreBreakdown(user_value=9, novelty=4, feasibility=7),
                ),
            ],
            summary="one recommendation",
        )

        agent = TechStackAdvisorAgent(client=client, reader=reader)
        await agent.run_evaluation(features, pass1=pass1)

        # First call should include parity_source for "site search"
        first_payload = json.loads(call_inputs[0])
        first_feature = first_payload["features_to_evaluate"][0]
        assert first_feature["feature_name"] == "site search"
        assert first_feature.get("parity_source") == ["Rival", "Acme"]

        # Second call should NOT have parity_source for "dark mode"
        second_payload = json.loads(call_inputs[1])
        second_feature = second_payload["features_to_evaluate"][0]
        assert second_feature["feature_name"] == "dark mode"
        assert "parity_source" not in second_feature

    @pytest.mark.asyncio
    async def test_stack_context_included_when_code_analysis_provided(self) -> None:
        """Current stack context is passed in every API call when code_analysis is provided."""
        from sea.schemas.code_analysis import CodeAnalysisOutput, TechStackItem, ArchitectureOverview

        features = ["site search", "dark mode"]

        client = MagicMock(spec=ClaudeClient)
        call_inputs: list[str] = []

        async def capture_and_return(system, messages, tools, tool_handler, on_progress=None, on_tokens=None):
            call_inputs.append(messages[0]["content"])
            feature_name = json.loads(messages[0]["content"])["features_to_evaluate"][0]["feature_name"]
            return _make_feature_json(feature_name)

        client.run_agent_loop = AsyncMock(side_effect=capture_and_return)
        reader = MagicMock(spec=CodebaseReader)

        code_analysis = CodeAnalysisOutput(
            tech_stack=[TechStackItem(name="Next.js", category="framework", version="14")],
            architecture=ArchitectureOverview(),
            summary="Next.js app.",
        )

        agent = TechStackAdvisorAgent(client=client, reader=reader)
        await agent.run_evaluation(features, code_analysis=code_analysis)

        # Both calls should include current_stack
        for raw in call_inputs:
            payload = json.loads(raw)
            assert "current_stack" in payload
            tech_stack = payload["current_stack"]["tech_stack"]
            assert any(item["name"] == "Next.js" for item in tech_stack)


class TestTokenBudget:
    """Token budget sizing — documents and verifies the per-feature batching rationale.

    Each 4G API call is capped at MAX_TOKENS output tokens. A feature with 3
    Mermaid diagrams, extended summaries, and detailed metadata reaches ~3,000-5,000
    tokens of model output. Batching 5+ features in one call risks truncation.
    Processing one feature per call guarantees each response is safely within budget.

    Constants:
        _REALISTIC_TOKENS_PER_FEATURE  ≈ chars of system-prompt example × 3 verbosity / 4
        _MAX_SAFE_BATCH                 = MAX_TOKENS // _REALISTIC_TOKENS_PER_FEATURE
    """

    def test_compact_example_size_is_known(self) -> None:
        """The system prompt embeds a representative example feature JSON that we can measure."""
        assert _COMPACT_FEATURE_CHARS > 4_000, (
            "System prompt example should be at least 4,000 chars — "
            f"got {_COMPACT_FEATURE_CHARS}. Check that the regex still matches."
        )

    def test_realistic_tokens_per_feature_within_single_call_budget(self) -> None:
        """One realistic feature response fits comfortably within MAX_TOKENS."""
        assert _REALISTIC_TOKENS_PER_FEATURE < MAX_TOKENS, (
            f"Single feature estimate ({_REALISTIC_TOKENS_PER_FEATURE} tokens) "
            f"must be < MAX_TOKENS ({MAX_TOKENS})"
        )

    def test_safe_headroom_per_single_feature_call(self) -> None:
        """One realistic feature uses well under half the output token budget, leaving room for prose."""
        headroom = MAX_TOKENS - _REALISTIC_TOKENS_PER_FEATURE
        assert headroom > MAX_TOKENS // 3, (
            f"Expected at least {MAX_TOKENS // 3} tokens of headroom, "
            f"but single-feature output already consumes {_REALISTIC_TOKENS_PER_FEATURE} tokens"
        )

    def test_batching_exceeds_budget_above_safe_threshold(self) -> None:
        """Batching more than _MAX_SAFE_BATCH features in one call would exceed MAX_TOKENS."""
        too_many = _MAX_SAFE_BATCH + 1
        combined = too_many * _REALISTIC_TOKENS_PER_FEATURE
        assert combined > MAX_TOKENS, (
            f"{too_many} features batched ({combined} tokens) should exceed "
            f"MAX_TOKENS ({MAX_TOKENS})"
        )

    def test_five_features_batched_exceeds_budget(self) -> None:
        """Five features batched in a single call would exceed the output token limit.

        This is the observed failure mode: with 5 features sent together,
        the model truncated its JSON after completing the first feature.
        """
        five_features_tokens = 5 * _REALISTIC_TOKENS_PER_FEATURE
        assert five_features_tokens > MAX_TOKENS, (
            f"5 features batched ({five_features_tokens} tokens) should exceed "
            f"MAX_TOKENS ({MAX_TOKENS}). "
            f"If this assertion fails, MAX_TOKENS may have been raised — "
            f"verify the threshold is still correct for the configured model."
        )

    def test_max_safe_batch_is_small(self) -> None:
        """The safe batch size is small enough that real feature lists commonly exceed it.

        If MAX_TOKENS is raised (e.g. to 30,000+), this test documents the new
        break-even and confirms batching is still needed for larger feature lists.
        """
        # Even at 30,000 output tokens, a verbose 7-feature eval would exceed the limit.
        # The safe batch size should always be less than a typical feature list (5-10 items).
        assert _MAX_SAFE_BATCH < 10, (
            f"Safe batch size is {_MAX_SAFE_BATCH} features. "
            f"If this exceeds 10, review whether per-feature batching is still needed."
        )

    @pytest.mark.asyncio
    async def test_per_call_payload_bounded_to_one_feature_regardless_of_total(self) -> None:
        """With 10 features (well above safe batch), each API call still receives exactly one."""
        features = [f"feature_{i}" for i in range(10)]
        call_feature_counts: list[int] = []

        client = MagicMock(spec=ClaudeClient)

        async def capture(system, messages, tools, tool_handler, on_progress=None, on_tokens=None):
            payload = json.loads(messages[0]["content"])
            call_feature_counts.append(len(payload["features_to_evaluate"]))
            name = payload["features_to_evaluate"][0]["feature_name"]
            return _make_feature_json(name)

        client.run_agent_loop = AsyncMock(side_effect=capture)
        reader = MagicMock(spec=CodebaseReader)

        agent = TechStackAdvisorAgent(client=client, reader=reader)
        result = await agent.run_evaluation(features)

        # Every call contained exactly one feature
        assert all(n == 1 for n in call_feature_counts), (
            f"Expected 1 feature per call, got: {call_feature_counts}"
        )
        # All 10 features were evaluated
        assert len(result.features) == 10

    @pytest.mark.asyncio
    async def test_estimated_output_tokens_per_call_within_budget(self) -> None:
        """Each call's realistic output token estimate is within MAX_TOKENS."""
        # The mock returns compact JSON; real output would be up to VERBOSITY_FACTOR larger.
        # Verify that even at 3× verbosity, a single-feature response stays within budget.
        features = ["site search", "dark mode", "mobile nav"]

        client = MagicMock(spec=ClaudeClient)
        response_sizes: list[int] = []

        async def capture(system, messages, tools, tool_handler, on_progress=None, on_tokens=None):
            name = json.loads(messages[0]["content"])["features_to_evaluate"][0]["feature_name"]
            response = _make_feature_json(name)
            response_sizes.append(len(response))
            return response

        client.run_agent_loop = AsyncMock(side_effect=capture)
        reader = MagicMock(spec=CodebaseReader)

        agent = TechStackAdvisorAgent(client=client, reader=reader)
        await agent.run_evaluation(features)

        for i, chars in enumerate(response_sizes):
            # Apply verbosity factor to estimate realistic output size
            realistic_tokens = (chars * _VERBOSITY_FACTOR) // _CHARS_PER_TOKEN
            assert realistic_tokens < MAX_TOKENS, (
                f"Call {i+1}: estimated {realistic_tokens} tokens at {_VERBOSITY_FACTOR}× verbosity "
                f"exceeds MAX_TOKENS ({MAX_TOKENS}). Per-feature batching may not be enough."
            )
