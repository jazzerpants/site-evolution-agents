"""Tests for HTML dashboard generation."""

from __future__ import annotations

import json
from pathlib import Path

from sea.output.dashboard import render_dashboard, _md_to_html
from sea.schemas.config import AnalysisConfig
from sea.schemas.pipeline import FinalReport
from sea.schemas.recommendations import Pass1Output, Recommendation, ScoreBreakdown
from sea.schemas.research import ComparativeResearchOutput, CompetitorProfile, GapItem
from sea.schemas.code_analysis import CodeAnalysisOutput, TechStackItem, ArchitectureOverview
from sea.schemas.tech_stack import (
    TechStackAdvisorOutput, TechStackRecommendation, TechApproach, ArchitectureDiagram,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_MERMAID_CURRENT = (
    "flowchart TD\n"
    "    classDef keep fill:#4ade80,stroke:#22c55e,color:#0f172a\n"
    "    classDef issue fill:#f87171,stroke:#ef4444,color:#0f172a\n"
    "    appRouter[Next.js App Router]:::keep\n"
    "    noSearch[No Search Capability]:::issue\n"
    "    appRouter --> noSearch"
)
_MERMAID_SIMPLE = (
    "flowchart TD\n"
    "    classDef keep fill:#4ade80,stroke:#22c55e,color:#0f172a\n"
    "    classDef new fill:#38bdf8,stroke:#0ea5e9,color:#0f172a\n"
    "    appRouter[Next.js App Router]:::keep\n"
    "    fuseJs[Fuse.js Client]:::new\n"
    "    searchUI[Search UI Component]:::new\n"
    "    appRouter --> searchUI\n"
    "    searchUI --> fuseJs"
)


def _make_tech_stack_advisor() -> TechStackAdvisorOutput:
    return TechStackAdvisorOutput(
        features=[
            TechStackRecommendation(
                feature_name="site search",
                parity_source=["Acme", "BetterDocs"],
                current_stack_compatibility="Client-side search fits natively.",
                simple_approach=TechApproach(
                    approach_name="simple",
                    description="Fuse.js over a pre-built JSON index",
                    tech_stack=["Fuse.js"],
                    new_dependencies=["fuse.js"],
                    architecture_fit="fits_as_is",
                    effort_estimate="2-3 days",
                    pros=["No server required"],
                    cons=["No query analytics"],
                ),
                comprehensive_approach=TechApproach(
                    approach_name="comprehensive",
                    description="Algolia with facets and analytics",
                    tech_stack=["Algolia", "react-instantsearch"],
                    new_dependencies=["algoliasearch"],
                    architecture_fit="minor_changes",
                    effort_estimate="1-2 weeks",
                    pros=["Typo tolerance", "Analytics"],
                    cons=["$50-500/month"],
                ),
                recommended_approach="simple",
                recommendation_rationale="Under 500 pages — Fuse.js is sufficient at zero cost.",
                diagrams=[
                    ArchitectureDiagram(
                        title="Current Architecture — Search Gap",
                        phase="current",
                        mermaid=_MERMAID_CURRENT,
                        summary="No search capability exists today (red). Everything else is healthy.",
                        components_to_keep=["Next.js App Router"],
                        components_with_issues=["No Search Capability"],
                    ),
                    ArchitectureDiagram(
                        title="Simple Approach — Fuse.js",
                        phase="simple",
                        mermaid=_MERMAID_SIMPLE,
                        summary="Blue items show what gets built. Green stays unchanged.",
                        components_to_keep=["Next.js App Router"],
                        new_components=["Fuse.js Client", "Search UI Component"],
                    ),
                ],
            )
        ],
        summary="One feature evaluated: site search.",
    )


def _make_report(tmp_path) -> FinalReport:
    return FinalReport(
        config=AnalysisConfig(
            target_path=str(tmp_path),
            priorities=["UX"],
            site_name="Dashboard Test",
        ),
        research=ComparativeResearchOutput(
            competitors=[
                CompetitorProfile(name="Rival", url="https://rival.com", relevance="Same niche"),
            ],
            gaps=[GapItem(description="No dark mode", severity="medium", competitors_with_feature=["Rival"])],
            summary="One competitor.",
        ),
        code_analysis=CodeAnalysisOutput(
            tech_stack=[TechStackItem(name="Next.js", category="framework", version="16")],
            architecture=ArchitectureOverview(),
            summary="Standard app.",
        ),
        recommendations=Pass1Output(
            recommendations=[
                Recommendation(
                    id="REC-001",
                    title="Add dark mode",
                    description="Add dark mode toggle",
                    category="quick-win",
                    estimated_complexity="low",
                    scores=ScoreBreakdown(user_value=8, novelty=3, feasibility=9),
                    rank=1,
                ),
                Recommendation(
                    id="REC-002",
                    title="Improve nav",
                    description="Redesign navigation",
                    category="medium-term",
                    estimated_complexity="medium",
                    scores=ScoreBreakdown(user_value=7, novelty=5, feasibility=6),
                    rank=2,
                ),
            ],
            quick_wins=["REC-001"],
            summary="Two recommendations.",
        ),
    )


class TestMdToHtml:
    def test_bold(self) -> None:
        assert "<strong>bold</strong>" in _md_to_html("**bold**")

    def test_italic(self) -> None:
        assert "<em>italic</em>" in _md_to_html("*italic*")

    def test_bullet_list(self) -> None:
        html = _md_to_html("- item1\n- item2")
        assert "<ul>" in html
        assert "<li>item1</li>" in html
        assert "<li>item2</li>" in html

    def test_empty_string(self) -> None:
        assert _md_to_html("") == ""


class TestRenderDashboard:
    def test_renders_html(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        html = render_dashboard(report)
        assert "<!DOCTYPE html>" in html
        assert "Dashboard Test" in html

    def test_includes_recommendations(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        html = render_dashboard(report)
        assert "REC-001" in html
        assert "Add dark mode" in html
        assert "REC-002" in html

    def test_includes_filter_buttons(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        html = render_dashboard(report)
        assert "Quick Wins" in html
        assert "Medium Term" in html

    def test_includes_competitors(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        html = render_dashboard(report)
        assert "Rival" in html

    def test_includes_tech_stack(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        html = render_dashboard(report)
        assert "Next.js" in html

    def test_includes_executive_summary(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        html = render_dashboard(report, executive_summary="Top priority is dark mode.")
        assert "Top priority is dark mode" in html

    def test_score_bars(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        html = render_dashboard(report)
        # Score bar widths should be present (8*10=80%, etc.)
        assert "80%" in html  # user_value=8

    def test_empty_report(self, tmp_path) -> None:
        report = FinalReport(
            config=AnalysisConfig(target_path=str(tmp_path), priorities=["test"]),
        )
        html = render_dashboard(report)
        assert "<!DOCTYPE html>" in html

    def test_collapsible_sections(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        html = render_dashboard(report)
        assert "toggle(this)" in html
        assert "section-header" in html


class TestTechStackAdvisorSection:
    def test_renders_feature_name(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        report.tech_stack_advisor = _make_tech_stack_advisor()
        html = render_dashboard(report)
        assert "Site Search" in html

    def test_renders_parity_banner(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        report.tech_stack_advisor = _make_tech_stack_advisor()
        html = render_dashboard(report)
        assert "Acme" in html
        assert "BetterDocs" in html
        assert "parity" in html.lower()

    def test_renders_approach_cards(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        report.tech_stack_advisor = _make_tech_stack_advisor()
        html = render_dashboard(report)
        assert "Fuse.js" in html
        assert "Algolia" in html
        assert "2-3 days" in html
        assert "1-2 weeks" in html

    def test_renders_diagram_tabs(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        report.tech_stack_advisor = _make_tech_stack_advisor()
        html = render_dashboard(report)
        # Phase tab buttons
        assert "📍 Current" in html
        assert "🟢 Simple" in html
        # Diagram IDs for JS
        assert 'id="dtabs-0"' in html
        assert 'id="dpanel-0-0"' in html
        assert 'id="dpanel-0-1"' in html

    def test_embeds_mermaid_source(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        report.tech_stack_advisor = _make_tech_stack_advisor()
        html = render_dashboard(report)
        assert "flowchart TD" in html
        assert "No Search Capability" in html
        assert "Fuse.js Client" in html

    def test_renders_legend(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        report.tech_stack_advisor = _make_tech_stack_advisor()
        html = render_dashboard(report)
        assert "Next.js App Router" in html  # components_to_keep
        assert "No Search Capability" in html  # components_with_issues
        assert "Fuse.js Client" in html  # new_components

    def test_renders_recommendation_rationale(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        report.tech_stack_advisor = _make_tech_stack_advisor()
        html = render_dashboard(report)
        assert "Under 500 pages" in html

    def test_no_section_when_no_tech_stack_advisor(self, tmp_path) -> None:
        report = _make_report(tmp_path)
        html = render_dashboard(report)
        assert "Tech Stack Recommendations" not in html

    def test_fixture_roundtrip(self) -> None:
        """Verify mock_report.json parses cleanly and renders without error."""
        raw = (FIXTURES_DIR / "report.json").read_text()
        report = FinalReport.model_validate_json(raw)
        assert report.tech_stack_advisor is not None
        assert len(report.tech_stack_advisor.features) == 2  # noqa: PLR2004
        # Both features have diagrams
        for feat in report.tech_stack_advisor.features:
            assert len(feat.diagrams) >= 2  # noqa: PLR2004
        html = render_dashboard(report)
        assert "Tech Stack Recommendations" in html
        assert "flowchart TD" in html
        assert "mermaid" in html
