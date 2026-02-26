"""Tests for the OrchestratorAgent — focused on report-building logic."""

from __future__ import annotations

from unittest.mock import AsyncMock

from sea.agents.orchestrator.agent import OrchestratorAgent
from sea.schemas.config import AnalysisConfig
from sea.schemas.feasibility import FeasibilityAssessment, FeasibilityOutput
from sea.schemas.recommendations import (
    Pass1Output,
    Pass2Output,
    Recommendation,
    ScoreBreakdown,
)


def _make_orchestrator(tmp_path) -> OrchestratorAgent:
    config = AnalysisConfig(target_path=str(tmp_path), priorities=["UX"])
    return OrchestratorAgent(client=AsyncMock(), config=config)


def _rec(id: str, title: str, rank: int) -> Recommendation:
    return Recommendation(
        id=id,
        title=title,
        description="desc",
        rank=rank,
        scores=ScoreBreakdown(user_value=5, novelty=5, feasibility=5),
    )


class TestFeasibilityIdRemapping:
    """Verify feasibility assessment IDs are remapped after Pass 2 re-ranking."""

    def test_ids_remapped_to_pass2_order(self, tmp_path) -> None:
        orch = _make_orchestrator(tmp_path)

        # Pass 1: A=REC-001, B=REC-002, C=REC-003
        orch.state.pass1 = Pass1Output(recommendations=[
            _rec("REC-001", "Feature A", 1),
            _rec("REC-002", "Feature B", 2),
            _rec("REC-003", "Feature C", 3),
        ])

        # Pass 2 re-ranks: C=REC-001, A=REC-002, B=REC-003
        orch.state.pass2 = Pass2Output(recommendations=[
            _rec("REC-001", "Feature C", 1),
            _rec("REC-002", "Feature A", 2),
            _rec("REC-003", "Feature B", 3),
        ])

        # Feasibility uses original Pass 1 IDs
        orch.state.feasibility = FeasibilityOutput(
            assessments=[
                FeasibilityAssessment(recommendation_id="REC-001", rating="easy", risk="low"),
                FeasibilityAssessment(recommendation_id="REC-002", rating="hard", risk="high"),
                FeasibilityAssessment(recommendation_id="REC-003", rating="moderate", risk="medium"),
            ],
            summary="test",
        )

        report = orch._build_report()

        # Feasibility IDs should now match Pass 2 IDs
        feas_map = {a.recommendation_id: a.rating for a in report.feasibility.assessments}

        # Feature A was REC-001 in Pass 1 (easy), now REC-002 in Pass 2
        assert feas_map["REC-002"] == "easy"
        # Feature B was REC-002 in Pass 1 (hard), now REC-003 in Pass 2
        assert feas_map["REC-003"] == "hard"
        # Feature C was REC-003 in Pass 1 (moderate), now REC-001 in Pass 2
        assert feas_map["REC-001"] == "moderate"

    def test_assessments_sorted_by_new_id(self, tmp_path) -> None:
        orch = _make_orchestrator(tmp_path)

        orch.state.pass1 = Pass1Output(recommendations=[
            _rec("REC-001", "Feature A", 1),
            _rec("REC-002", "Feature B", 2),
        ])
        orch.state.pass2 = Pass2Output(recommendations=[
            _rec("REC-001", "Feature B", 1),
            _rec("REC-002", "Feature A", 2),
        ])
        orch.state.feasibility = FeasibilityOutput(
            assessments=[
                FeasibilityAssessment(recommendation_id="REC-001", rating="easy"),
                FeasibilityAssessment(recommendation_id="REC-002", rating="hard"),
            ],
            summary="test",
        )

        report = orch._build_report()
        ids = [a.recommendation_id for a in report.feasibility.assessments]
        assert ids == ["REC-001", "REC-002"]

    def test_no_remapping_when_no_pass2(self, tmp_path) -> None:
        """If Pass 2 didn't run, feasibility IDs stay as-is."""
        orch = _make_orchestrator(tmp_path)

        orch.state.pass1 = Pass1Output(recommendations=[
            _rec("REC-001", "Feature A", 1),
        ])
        orch.state.feasibility = FeasibilityOutput(
            assessments=[
                FeasibilityAssessment(recommendation_id="REC-001", rating="easy"),
            ],
            summary="test",
        )

        report = orch._build_report()
        assert report.feasibility.assessments[0].recommendation_id == "REC-001"
        assert report.feasibility.assessments[0].rating == "easy"

    def test_no_remapping_when_no_feasibility(self, tmp_path) -> None:
        """If feasibility didn't run, report still builds fine."""
        orch = _make_orchestrator(tmp_path)

        orch.state.pass1 = Pass1Output(recommendations=[
            _rec("REC-001", "Feature A", 1),
        ])
        orch.state.pass2 = Pass2Output(recommendations=[
            _rec("REC-001", "Feature A", 1),
        ])

        report = orch._build_report()
        assert report.feasibility is None
