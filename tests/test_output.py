"""Tests for Markdown report generation."""

from __future__ import annotations

from sea.output.markdown import render_markdown_report
from sea.schemas.config import AnalysisConfig, Constraints
from sea.schemas.code_analysis import (
    CodeAnalysisOutput,
    TechStackItem,
    ArchitectureOverview,
    TechDebtItem,
)
from sea.schemas.pipeline import FinalReport
from sea.schemas.recommendations import Pass1Output, Recommendation, ScoreBreakdown
from sea.schemas.research import (
    ComparativeResearchOutput,
    CompetitorProfile,
    FeatureMatrixEntry,
    GapItem,
)


def _make_report(tmp_path) -> FinalReport:
    """Build a sample FinalReport for testing."""
    return FinalReport(
        config=AnalysisConfig(
            target_path=str(tmp_path),
            priorities=["UX", "Performance"],
            site_name="Test Site",
        ),
        research=ComparativeResearchOutput(
            competitors=[
                CompetitorProfile(
                    name="Rival",
                    url="https://rival.com",
                    relevance="Same niche",
                    strengths=["Fast"],
                    weaknesses=["Ugly"],
                ),
            ],
            feature_matrix=[
                FeatureMatrixEntry(
                    feature="Dark mode",
                    current_site="no",
                    competitors={"Rival": "yes"},
                ),
            ],
            gaps=[
                GapItem(
                    description="No dark mode",
                    severity="medium",
                    competitors_with_feature=["Rival"],
                ),
            ],
            summary="One competitor analyzed.",
        ),
        code_analysis=CodeAnalysisOutput(
            tech_stack=[
                TechStackItem(
                    name="Next.js",
                    category="framework",
                    version="16",
                    ux_pros=["Fast"],
                    ux_cons=["Complex"],
                ),
            ],
            architecture=ArchitectureOverview(
                routing_pattern="App Router",
                mermaid_diagram="graph TD; A-->B;",
            ),
            tech_debt=[
                TechDebtItem(
                    description="No error boundaries",
                    severity="medium",
                    location="src/",
                    suggestion="Add error boundaries",
                ),
            ],
            summary="Standard Next.js app.",
        ),
        recommendations=Pass1Output(
            recommendations=[
                Recommendation(
                    id="REC-001",
                    title="Add dark mode",
                    description="Toggle dark mode",
                    rationale="Users want it",
                    category="quick-win",
                    estimated_complexity="low",
                    expected_impact="High satisfaction",
                    scores=ScoreBreakdown(user_value=8, novelty=3, feasibility=9),
                    rank=1,
                ),
            ],
            quick_wins=["REC-001"],
            summary="One recommendation.",
        ),
    )


class TestMarkdownReport:
    def test_renders_title(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        md = render_markdown_report(report)
        assert "# Site Evolution Report: Test Site" in md

    def test_renders_executive_summary(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        md = render_markdown_report(report, executive_summary="This is the summary.")
        assert "## Executive Summary" in md
        assert "This is the summary." in md

    def test_renders_tech_stack_table(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        md = render_markdown_report(report)
        assert "| Next.js |" in md
        assert "framework" in md

    def test_renders_recommendations(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        md = render_markdown_report(report)
        assert "REC-001" in md
        assert "Add dark mode" in md
        assert "User Value: 8/10" in md

    def test_renders_feature_matrix(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        md = render_markdown_report(report)
        assert "Dark mode" in md
        assert "Rival" in md

    def test_renders_gaps(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        md = render_markdown_report(report)
        assert "No dark mode" in md

    def test_renders_tech_debt(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        md = render_markdown_report(report)
        assert "No error boundaries" in md

    def test_renders_mermaid_diagram(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        md = render_markdown_report(report)
        assert "```mermaid" in md

    def test_empty_report_still_renders(self, tmp_path) -> None:
        report = FinalReport(
            config=AnalysisConfig(target_path=str(tmp_path), priorities=["test"]),
        )
        md = render_markdown_report(report)
        assert "# Site Evolution Report" in md
