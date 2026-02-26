"""Markdown report builder — renders FinalReport to a structured Markdown document."""

from __future__ import annotations

from sea.schemas.pipeline import FinalReport


def render_markdown_report(report: FinalReport, *, executive_summary: str = "") -> str:
    """Render a FinalReport into a Markdown string."""
    sections: list[str] = []

    # Title
    site_name = report.config.site_name or report.config.target_url or report.config.target_path
    sections.append(f"# Site Evolution Report: {site_name}\n")
    sections.append(f"*Generated: {report.generated_at}*\n")

    # Executive Summary
    if executive_summary:
        sections.append("## Executive Summary\n")
        sections.append(executive_summary + "\n")

    # Configuration
    sections.append("## Analysis Configuration\n")
    sections.append(f"- **Target path:** {report.config.target_path or 'N/A'}")
    sections.append(f"- **Target URL:** {report.config.target_url or 'N/A'}")
    sections.append("- **Priorities:**")
    for p in report.config.priorities:
        sections.append(f"  - {p}")
    if report.config.constraints.must_keep:
        sections.append(f"- **Must keep:** {', '.join(report.config.constraints.must_keep)}")
    if report.config.constraints.budget:
        sections.append(f"- **Budget:** {report.config.constraints.budget}")
    sections.append("")

    # Comparative Research
    if report.research:
        sections.append("## Comparative Research\n")
        sections.append(f"{report.research.summary}\n")

        if report.research.competitors:
            sections.append("### Competitors Analyzed\n")
            for comp in report.research.competitors:
                sections.append(f"#### {comp.name} ({comp.url})")
                sections.append(f"*{comp.relevance}*\n")
                if comp.strengths:
                    sections.append("**Strengths:**")
                    for s in comp.strengths:
                        sections.append(f"- {s}")
                if comp.weaknesses:
                    sections.append("**Weaknesses:**")
                    for w in comp.weaknesses:
                        sections.append(f"- {w}")
                sections.append("")

        if report.research.feature_matrix:
            sections.append("### Feature Matrix\n")
            sections.append(_render_feature_matrix(report))

        if report.research.gaps:
            sections.append("### Gaps Identified\n")
            for gap in report.research.gaps:
                severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(gap.severity, "⚪")
                sections.append(f"- {severity_icon} **{gap.description}** (seen in: {', '.join(gap.competitors_with_feature)})")
            sections.append("")

        if report.research.ux_patterns:
            sections.append("### UX Patterns Observed\n")
            for pat in report.research.ux_patterns:
                sections.append(f"- **{pat.name}**: {pat.description} (seen in: {', '.join(pat.seen_in)})")
            sections.append("")

    # Code Analysis
    if report.code_analysis:
        sections.append("## Code Analysis\n")
        sections.append(f"{report.code_analysis.summary}\n")

        if report.code_analysis.tech_stack:
            sections.append("### Tech Stack\n")
            sections.append("| Technology | Category | Version | UX Pros | UX Cons |")
            sections.append("|-----------|----------|---------|---------|---------|")
            for t in report.code_analysis.tech_stack:
                pros = ", ".join(t.ux_pros) if t.ux_pros else "—"
                cons = ", ".join(t.ux_cons) if t.ux_cons else "—"
                sections.append(f"| {t.name} | {t.category} | {t.version} | {pros} | {cons} |")
            sections.append("")

        if report.code_analysis.architecture.mermaid_diagram:
            sections.append("### Architecture Diagram\n")
            sections.append(f"```mermaid\n{report.code_analysis.architecture.mermaid_diagram}\n```\n")

        if report.code_analysis.tech_debt:
            sections.append("### Tech Debt\n")
            for debt in report.code_analysis.tech_debt:
                severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(debt.severity, "⚪")
                sections.append(f"- {severity_icon} **{debt.description}** ({debt.location})")
                if debt.suggestion:
                    sections.append(f"  - Suggestion: {debt.suggestion}")
            sections.append("")

    # Recommendations
    recs = report.recommendations
    if recs:
        sections.append("## Recommendations\n")
        sections.append(f"{recs.summary}\n")

        sections.append("### Ranked Recommendations\n")
        sorted_recs = sorted(recs.recommendations, key=lambda r: r.rank)
        for rec in sorted_recs:
            scores = rec.scores
            sections.append(f"#### #{rec.rank}: {rec.title} (`{rec.id}`)\n")
            sections.append(f"**Category:** {rec.category} | **Complexity:** {rec.estimated_complexity}\n")
            sections.append(f"{rec.description}\n")
            if rec.rationale:
                sections.append(f"*Rationale: {rec.rationale}*\n")
            sections.append(f"**Scores:** User Value: {scores.user_value}/10 | Novelty: {scores.novelty}/10 | Feasibility: {scores.feasibility}/10\n")

        # Quick wins callout
        quick_ids = getattr(recs, "quick_wins", [])
        if quick_ids:
            sections.append("### Quick Wins\n")
            for rec in sorted_recs:
                if rec.id in quick_ids:
                    sections.append(f"- **{rec.title}** (`{rec.id}`) — {rec.expected_impact}")
            sections.append("")

    # Feasibility
    if report.feasibility:
        sections.append("## Feasibility Assessment\n")
        sections.append(f"{report.feasibility.summary}\n")

        sections.append("| Rec ID | Rating | Cost | Dev Days | Risk |")
        sections.append("|--------|--------|------|----------|------|")
        for a in report.feasibility.assessments:
            sections.append(f"| {a.recommendation_id} | {a.rating} | {a.cost_estimate} | {a.developer_days} | {a.risk} |")
        sections.append("")

    # Quality Audit
    if report.quality_audit:
        qa = report.quality_audit
        sections.append("## Quality Audit\n")
        sections.append(f"{qa.summary}\n")

        if qa.accessibility.issues:
            sections.append("### Accessibility Issues\n")
            for issue in qa.accessibility.issues:
                sections.append(f"- **[{issue.severity}]** {issue.description} (WCAG {issue.wcag_criterion})")
                if issue.suggestion:
                    sections.append(f"  - Fix: {issue.suggestion}")
            sections.append("")

        if qa.performance.metrics:
            sections.append("### Performance Metrics\n")
            sections.append("| Metric | Value | Rating |")
            sections.append("|--------|-------|--------|")
            for m in qa.performance.metrics:
                sections.append(f"| {m.name} | {m.value} | {m.rating} |")
            sections.append("")

        if qa.priority_issues:
            sections.append("### Priority Issues\n")
            for issue in qa.priority_issues:
                sections.append(f"- **[{issue.impact}]** {issue.description} ({issue.category})")
            sections.append("")

    # UX & Design
    if report.ux_design:
        ux = report.ux_design
        sections.append("## UX & Design\n")
        sections.append(f"{ux.summary}\n")

        if ux.overall_impression:
            sections.append(f"**Overall Impression:** {ux.overall_impression}\n")

        if ux.strengths:
            sections.append("### Strengths\n")
            for s in ux.strengths:
                sections.append(f"- {s}")
            sections.append("")

        sections.append("### Layout & Visual Hierarchy\n")
        if ux.layout.visual_hierarchy:
            sections.append(f"- **Visual Hierarchy:** {ux.layout.visual_hierarchy}")
        if ux.layout.whitespace_usage:
            sections.append(f"- **Whitespace:** {ux.layout.whitespace_usage}")
        if ux.layout.grid_consistency:
            sections.append(f"- **Grid:** {ux.layout.grid_consistency}")
        if ux.layout.responsive_notes:
            sections.append(f"- **Responsive:** {ux.layout.responsive_notes}")
        sections.append("")

        sections.append("### Typography\n")
        if ux.typography.readability:
            sections.append(f"- **Readability:** {ux.typography.readability}")
        if ux.typography.hierarchy:
            sections.append(f"- **Hierarchy:** {ux.typography.hierarchy}")
        if ux.typography.consistency:
            sections.append(f"- **Consistency:** {ux.typography.consistency}")
        sections.append("")

        sections.append("### Color\n")
        if ux.color.palette_coherence:
            sections.append(f"- **Palette:** {ux.color.palette_coherence}")
        if ux.color.contrast_notes:
            sections.append(f"- **Contrast:** {ux.color.contrast_notes}")
        if ux.color.brand_consistency:
            sections.append(f"- **Brand:** {ux.color.brand_consistency}")
        if ux.color.dark_mode_notes:
            sections.append(f"- **Dark Mode:** {ux.color.dark_mode_notes}")
        sections.append("")

        sections.append("### Navigation\n")
        if ux.navigation.clarity:
            sections.append(f"- **Clarity:** {ux.navigation.clarity}")
        if ux.navigation.information_architecture:
            sections.append(f"- **Information Architecture:** {ux.navigation.information_architecture}")
        if ux.navigation.mobile_notes:
            sections.append(f"- **Mobile:** {ux.navigation.mobile_notes}")
        sections.append("")

        if ux.issues:
            sections.append("### Design Issues\n")
            severity_order = {"critical": 0, "major": 1, "minor": 2, "suggestion": 3}
            sorted_issues = sorted(ux.issues, key=lambda i: severity_order.get(i.severity, 4))
            for issue in sorted_issues:
                severity_icon = {"critical": "\U0001f534", "major": "\U0001f7e1", "minor": "\U0001f7e2", "suggestion": "\u26aa"}.get(issue.severity, "\u26aa")
                sections.append(f"- {severity_icon} **[{issue.area}]** {issue.description}")
                if issue.recommendation:
                    sections.append(f"  - Recommendation: {issue.recommendation}")
                if issue.competitors_doing_better:
                    sections.append(f"  - Competitors doing better: {', '.join(issue.competitors_doing_better)}")
            sections.append("")

    # Tech Stack Advisor
    if report.tech_stack_advisor:
        tsa = report.tech_stack_advisor
        sections.append("## Tech Stack Recommendations\n")
        sections.append(f"{tsa.summary}\n")

        for feat in tsa.features:
            sections.append(f"### {feat.feature_name.title()}\n")

            if feat.parity_source:
                sections.append(f"**Competitor parity:** {', '.join(feat.parity_source)} already offer this feature.\n")

            sections.append(f"{feat.current_stack_compatibility}\n")

            # Architecture diagrams
            for diagram in feat.diagrams:
                sections.append(f"#### {diagram.title}\n")
                sections.append(f"{diagram.summary}\n")

                if diagram.components_to_keep:
                    sections.append(f"- **Keep (green):** {', '.join(diagram.components_to_keep)}")
                if diagram.components_with_issues:
                    sections.append(f"- **Issues (red):** {', '.join(diagram.components_with_issues)}")
                if diagram.components_to_modify:
                    sections.append(f"- **Modify (yellow):** {', '.join(diagram.components_to_modify)}")
                if diagram.new_components:
                    sections.append(f"- **New (blue):** {', '.join(diagram.new_components)}")
                sections.append("")

                sections.append(f"```mermaid\n{diagram.mermaid}\n```\n")

            # Approach detail tables
            s = feat.simple_approach
            sections.append(f"#### Simple Approach: {s.description}\n")
            sections.append(f"| | |")
            sections.append(f"|---|---|")
            sections.append(f"| **Stack** | {', '.join(s.tech_stack)} |")
            sections.append(f"| **New dependencies** | {', '.join(s.new_dependencies) or 'None'} |")
            sections.append(f"| **Architecture fit** | {s.architecture_fit} |")
            sections.append(f"| **Effort** | {s.effort_estimate} |")
            if s.pros:
                sections.append(f"| **Pros** | {', '.join(s.pros)} |")
            if s.cons:
                sections.append(f"| **Cons** | {', '.join(s.cons)} |")
            sections.append("")

            if feat.comprehensive_approach:
                c = feat.comprehensive_approach
                sections.append(f"#### Comprehensive Approach: {c.description}\n")
                sections.append(f"| | |")
                sections.append(f"|---|---|")
                sections.append(f"| **Stack** | {', '.join(c.tech_stack)} |")
                sections.append(f"| **New dependencies** | {', '.join(c.new_dependencies) or 'None'} |")
                sections.append(f"| **Architecture fit** | {c.architecture_fit} |")
                sections.append(f"| **Effort** | {c.effort_estimate} |")
                if c.architecture_changes:
                    sections.append(f"| **Architecture changes** | {', '.join(c.architecture_changes)} |")
                if c.pros:
                    sections.append(f"| **Pros** | {', '.join(c.pros)} |")
                if c.cons:
                    sections.append(f"| **Cons** | {', '.join(c.cons)} |")
                sections.append("")

            sections.append(f"**Recommendation:** {feat.recommended_approach} — {feat.recommendation_rationale}\n")

    # Footer
    sections.append("---\n")
    sections.append("*Report generated by [Site Evolution Agents](https://github.com/site-evolution-agents)*")

    return "\n".join(sections)


def _render_feature_matrix(report: FinalReport) -> str:
    """Render the feature matrix as a Markdown table."""
    if not report.research or not report.research.feature_matrix:
        return ""

    # Collect all competitor names
    all_competitors: set[str] = set()
    for entry in report.research.feature_matrix:
        all_competitors.update(entry.competitors.keys())
    competitor_names = sorted(all_competitors)

    # Header
    header = "| Feature | Current Site | " + " | ".join(competitor_names) + " |"
    separator = "|---------|-------------|" + "|".join(["---"] * len(competitor_names)) + "|"

    rows = [header, separator]
    for entry in report.research.feature_matrix:
        vals = [entry.competitors.get(name, "?") for name in competitor_names]
        row = f"| {entry.feature} | {entry.current_site} | " + " | ".join(vals) + " |"
        rows.append(row)

    return "\n".join(rows) + "\n"
