"""Static HTML dashboard generator — renders FinalReport to a self-contained HTML file."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markdown_it import MarkdownIt

from sea.schemas.pipeline import FinalReport

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_md = MarkdownIt()


def _md_to_html(text: str) -> str:
    """Convert Markdown to HTML using markdown-it-py."""
    return _md.render(text)


def render_dashboard(
    report: FinalReport,
    *,
    executive_summary: str = "",
    screenshot_paths: list[dict] | None = None,
) -> str:
    """Render a FinalReport into a self-contained HTML dashboard.

    If ``screenshot_paths`` is provided (list of ``{url, tile_paths}`` dicts),
    the dashboard references local files instead of inlining base64.  This
    keeps the HTML small and lets the user browse screenshots independently.
    """
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("dashboard.html")

    site_name = report.config.site_name or report.config.target_url or report.config.target_path

    # Prepare recommendations list for the template
    recs_data = None
    if report.recommendations:
        recs_data = sorted(
            [r.model_dump() for r in report.recommendations.recommendations],
            key=lambda r: r["rank"],
        )

    # Prefer file paths over inline base64 for screenshots
    screenshots_data = None
    if screenshot_paths:
        screenshots_data = screenshot_paths
    elif report.screenshots:
        # Fallback: inline base64 (e.g. when called without saving to disk)
        screenshots_data = [s.model_dump() for s in report.screenshots]

    # Convert follow-up QA answers from Markdown to HTML
    feasibility_data = None
    if report.feasibility:
        feasibility_data = report.feasibility.model_dump()
        for qa in feasibility_data.get("follow_up_qa", []):
            qa["answer_html"] = _md_to_html(qa.get("answer", ""))

    return template.render(
        site_name=site_name,
        generated_at=report.generated_at,
        executive_summary=executive_summary,
        executive_summary_html=_md_to_html(executive_summary) if executive_summary else "",
        recommendations=recs_data,
        research=report.research.model_dump() if report.research else None,
        code_analysis=report.code_analysis.model_dump() if report.code_analysis else None,
        feasibility=feasibility_data,
        quality_audit=report.quality_audit.model_dump() if report.quality_audit else None,
        tech_stack_advisor=report.tech_stack_advisor.model_dump() if report.tech_stack_advisor else None,
        ux_design=report.ux_design.model_dump() if report.ux_design else None,
        screenshots=screenshots_data,
    )
