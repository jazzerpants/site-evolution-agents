"""Tests for the 4C Feature Recommender agent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from sea.agents.feature_recommender.agent import FeatureRecommenderAgent
from sea.schemas.recommendations import Pass1Output, Pass2Output, Recommendation, ScoreBreakdown
from sea.shared.claude_client import ClaudeClient


SAMPLE_PASS1 = {
    "recommendations": [
        {
            "id": "REC-001",
            "title": "Add dark mode",
            "description": "Implement system-wide dark mode toggle",
            "rationale": "All competitors have it",
            "category": "quick-win",
            "estimated_complexity": "low",
            "expected_impact": "High user satisfaction",
            "scores": {"user_value": 8, "novelty": 3, "feasibility": 9},
            "rank": 1,
        },
        {
            "id": "REC-002",
            "title": "Improve navigation",
            "description": "Redesign main navigation for mobile",
            "rationale": "Poor mobile experience",
            "category": "medium-term",
            "estimated_complexity": "medium",
            "expected_impact": "Improved mobile engagement",
            "scores": {"user_value": 9, "novelty": 4, "feasibility": 7},
            "rank": 2,
        },
    ],
    "quick_wins": ["REC-001"],
    "long_term": [],
    "summary": "Two key recommendations identified.",
}

SAMPLE_PASS2 = {
    "recommendations": [
        {
            "id": "REC-002",
            "title": "Improve navigation",
            "description": "Redesign main navigation for mobile",
            "rationale": "Critical for mobile users",
            "category": "medium-term",
            "estimated_complexity": "medium",
            "expected_impact": "Improved mobile engagement",
            "scores": {"user_value": 9, "novelty": 4, "feasibility": 8},
            "rank": 1,
        },
        {
            "id": "REC-001",
            "title": "Add dark mode",
            "description": "Implement system-wide dark mode toggle",
            "rationale": "All competitors have it",
            "category": "quick-win",
            "estimated_complexity": "low",
            "expected_impact": "High user satisfaction",
            "scores": {"user_value": 8, "novelty": 3, "feasibility": 9},
            "rank": 2,
        },
    ],
    "promoted": ["REC-002"],
    "demoted": ["REC-001"],
    "quick_wins": ["REC-001"],
    "long_term": [],
    "summary": "Navigation improvement promoted after feasibility review.",
}


class TestPass1Schema:
    def test_parse(self) -> None:
        output = Pass1Output(**SAMPLE_PASS1)
        assert len(output.recommendations) == 2
        assert output.recommendations[0].id == "REC-001"
        assert output.quick_wins == ["REC-001"]

    def test_round_trip(self) -> None:
        output = Pass1Output(**SAMPLE_PASS1)
        restored = Pass1Output.model_validate_json(output.model_dump_json())
        assert restored.recommendations[0].scores.user_value == 8


class TestPass2Schema:
    def test_parse(self) -> None:
        output = Pass2Output(**SAMPLE_PASS2)
        assert output.promoted == ["REC-002"]
        assert output.demoted == ["REC-001"]

    def test_round_trip(self) -> None:
        output = Pass2Output(**SAMPLE_PASS2)
        restored = Pass2Output.model_validate_json(output.model_dump_json())
        assert restored.recommendations[0].rank == 1


class TestFeatureRecommenderAgent:
    def test_agent_has_no_tools(self) -> None:
        client = ClaudeClient.__new__(ClaudeClient)
        agent = FeatureRecommenderAgent(client=client)
        assert agent.get_tools() == []
        assert agent.name == "4C Feature Recommender"
