"""Static HTML dashboard generator — renders FinalReport to a self-contained HTML file."""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from sea.schemas.pipeline import FinalReport

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _md_to_html(text: str) -> str:
    """Minimal markdown-to-HTML for the executive summary (no dependency)."""
    # Convert **bold**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Convert *italic*
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)

    lines = text.split("\n")
    result: list[str] = []
    in_ul = False
    in_ol = False

    def _close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            result.append("</ul>")
            in_ul = False
        if in_ol:
            result.append("</ol>")
            in_ol = False

    for line in lines:
        stripped = line.strip()

        # Headings: # … ####
        heading_match = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading_match:
            _close_lists()
            level = len(heading_match.group(1))
            result.append(f"<h{level}>{heading_match.group(2)}</h{level}>")
            continue

        # Unordered list items: - text
        if stripped.startswith("- "):
            if in_ol:
                result.append("</ol>")
                in_ol = False
            if not in_ul:
                result.append("<ul>")
                in_ul = True
            result.append(f"<li>{stripped[2:]}</li>")
            continue

        # Ordered list items: 1. text
        ol_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ol_match:
            if in_ul:
                result.append("</ul>")
                in_ul = False
            if not in_ol:
                result.append("<ol>")
                in_ol = True
            result.append(f"<li>{ol_match.group(1)}</li>")
            continue

        # Blank line or regular paragraph
        if not stripped and (in_ul or in_ol):
            # Blank line inside a list — keep the list open (markdown
            # often separates list items with blank lines).
            continue
        _close_lists()
        if stripped:
            result.append(f"<p>{stripped}</p>")

    _close_lists()
    return "\n".join(result)


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

    return template.render(
        site_name=site_name,
        generated_at=report.generated_at,
        executive_summary=executive_summary,
        executive_summary_html=_md_to_html(executive_summary) if executive_summary else "",
        recommendations=recs_data,
        research=report.research.model_dump() if report.research else None,
        code_analysis=report.code_analysis.model_dump() if report.code_analysis else None,
        feasibility=report.feasibility.model_dump() if report.feasibility else None,
        quality_audit=report.quality_audit.model_dump() if report.quality_audit else None,
        ux_design=report.ux_design.model_dump() if report.ux_design else None,
        screenshots=screenshots_data,
    )
