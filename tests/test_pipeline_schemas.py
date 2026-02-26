"""Tests for the pipeline state and final report schemas."""

from __future__ import annotations

from sea.schemas.config import AnalysisConfig
from sea.schemas.pipeline import FinalReport, PipelineState
from sea.schemas.code_analysis import CodeAnalysisOutput, ArchitectureOverview
from sea.schemas.feasibility import FeasibilityOutput, FeasibilityAssessment
from sea.schemas.quality import QualityAuditOutput
from sea.schemas.recommendations import Pass1Output, Pass2Output, Recommendation, ScoreBreakdown
from sea.schemas.research import ComparativeResearchOutput, CompetitorProfile


class TestPipelineState:
    def test_initial_state(self, tmp_path) -> None:
        cfg = AnalysisConfig(target_path=str(tmp_path), priorities=["ux"])
        state = PipelineState(config=cfg)
        assert state.research is None
        assert state.code_analysis is None
        assert state.pass1 is None
        assert state.feasibility is None
        assert state.quality_audit is None
        assert state.pass2 is None

    def test_state_with_all_fields(self, tmp_path) -> None:
        cfg = AnalysisConfig(target_path=str(tmp_path), priorities=["ux"])
        state = PipelineState(
            config=cfg,
            research=ComparativeResearchOutput(competitors=[]),
            code_analysis=CodeAnalysisOutput(tech_stack=[], architecture=ArchitectureOverview()),
            pass1=Pass1Output(recommendations=[], summary=""),
            feasibility=FeasibilityOutput(assessments=[]),
            quality_audit=QualityAuditOutput(),
            pass2=Pass2Output(recommendations=[], summary=""),
        )
        assert state.research is not None
        assert state.pass2 is not None


class TestFinalReport:
    def test_minimal_report(self, tmp_path) -> None:
        report = FinalReport(
            config=AnalysisConfig(target_path=str(tmp_path), priorities=["test"]),
        )
        assert report.generated_at is not None
        assert report.research is None

    def test_full_report_round_trip(self, tmp_path) -> None:
        report = FinalReport(
            config=AnalysisConfig(target_path=str(tmp_path), priorities=["test"]),
            research=ComparativeResearchOutput(
                competitors=[CompetitorProfile(name="R", url="https://r.com")],
                summary="done",
            ),
            code_analysis=CodeAnalysisOutput(
                tech_stack=[],
                architecture=ArchitectureOverview(),
                summary="analyzed",
            ),
            recommendations=Pass1Output(
                recommendations=[
                    Recommendation(
                        id="REC-001",
                        title="Test",
                        description="Desc",
                        scores=ScoreBreakdown(user_value=5, novelty=5, feasibility=5),
                        rank=1,
                    ),
                ],
                summary="recs",
            ),
            feasibility=FeasibilityOutput(
                assessments=[
                    FeasibilityAssessment(recommendation_id="REC-001", rating="easy"),
                ],
                summary="feasible",
            ),
            quality_audit=QualityAuditOutput(summary="quality ok"),
        )

        # Round trip through JSON
        json_str = report.model_dump_json()
        restored = FinalReport.model_validate_json(json_str)
        assert restored.research.competitors[0].name == "R"
        assert restored.recommendations.recommendations[0].id == "REC-001"
        assert restored.feasibility.assessments[0].rating == "easy"
