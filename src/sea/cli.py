"""Typer CLI — ``sea analyze`` and ``sea validate`` commands."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

from sea.config import load_config

# Load .env file from project root (if it exists)
load_dotenv()

app = typer.Typer(
    name="sea",
    help="Site Evolution Agents — analyze websites and produce evolution recommendations.",
    no_args_is_help=True,
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # httpx logs every HTTP request at INFO — noisy and unhelpful for users
    logging.getLogger("httpx").setLevel(logging.WARNING)


@app.command()
def validate(
    config: Path = typer.Option(..., "--config", "-c", help="Path to analysis-config.yml"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Validate a configuration file without running the analysis."""
    _setup_logging(verbose)

    try:
        cfg = load_config(config)
    except Exception as exc:
        console.print(f"[red]Config validation failed:[/] {exc}")
        raise typer.Exit(code=1)

    console.print("[green]Config is valid![/]\n")
    console.print(f"  Target path: {cfg.target_path or '(none)'}")
    console.print(f"  Target URL:  {cfg.target_url or '(none)'}")
    console.print(f"  Priorities:  {len(cfg.priorities)}")
    for p in cfg.priorities:
        console.print(f"    - {p}")
    if cfg.constraints.must_keep:
        console.print(f"  Must keep:   {cfg.constraints.must_keep}")
    if cfg.constraints.must_avoid:
        console.print(f"  Must avoid:  {cfg.constraints.must_avoid}")
    if cfg.constraints.budget:
        console.print(f"  Budget:      {cfg.constraints.budget}")
    console.print(f"  Output dir:  {cfg.output_directory}")


@app.command()
def analyze(
    config: Path = typer.Option(..., "--config", "-c", help="Path to analysis-config.yml"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run the full pipeline with mock data (no API calls)."),
) -> None:
    """Run the full analysis pipeline."""
    _setup_logging(verbose)

    try:
        cfg = load_config(config)
    except Exception as exc:
        console.print(f"[red]Config validation failed:[/] {exc}")
        raise typer.Exit(code=1)

    if dry_run:
        console.print("[yellow]DRY-RUN mode — no API calls will be made.[/]\n")

    console.print(f"[bold]Starting analysis pipeline for:[/] {cfg.site_name or cfg.target_path or cfg.target_url}\n")

    asyncio.run(_run_pipeline(cfg, dry_run=dry_run))


@app.command()
def feature(
    name: list[str] = typer.Option(..., "--name", "-n", help="Feature to evaluate (repeatable, e.g. --name search --name auth)."),
    config: Path = typer.Option(..., "--config", "-c", help="Path to analysis-config.yml"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run with mock data (no API calls)."),
    patch_report: Path = typer.Option(None, "--patch-report", help="Output directory containing report.json — patch it with 4G results and re-render the dashboard."),
) -> None:
    """Evaluate specific features — simple vs comprehensive approach + tech stack recommendations.

    Examples:

        sea feature --name search --config config/analysis-config.yml

        sea feature --name search --name auth --config config/analysis-config.yml

        sea feature --name search --config config/analysis-config.yml --patch-report ./output
    """
    _setup_logging(verbose)

    try:
        cfg = load_config(config)
    except Exception as exc:
        console.print(f"[red]Config validation failed:[/] {exc}")
        raise typer.Exit(code=1)

    if not cfg.target_path:
        console.print("[red]Error:[/] feature evaluation requires a codebase (target_path must be set in config).")
        raise typer.Exit(code=1)

    if patch_report and not (patch_report / "report.json").exists():
        console.print(f"[red]No report.json found in {patch_report}[/]")
        raise typer.Exit(code=1)

    if dry_run:
        console.print("[yellow]DRY-RUN mode — no API calls will be made.[/]\n")

    console.print(f"[bold]Evaluating feature(s):[/] {', '.join(name)}\n")
    asyncio.run(_run_feature_evaluation(cfg, features=list(name), dry_run=dry_run, patch_report=patch_report))


async def _run_pipeline(cfg: "AnalysisConfig", *, dry_run: bool = False) -> None:  # noqa: F821
    """Run the orchestrator pipeline."""
    from sea.agents.orchestrator.agent import OrchestratorAgent

    if dry_run:
        from sea.shared.claude_client import DryRunClient
        client = DryRunClient()
    else:
        from sea.shared.claude_client import ClaudeClient
        client = ClaudeClient()

    orchestrator = OrchestratorAgent(client=client, config=cfg)
    await orchestrator.run()


@app.command()
def render(
    output: Path = typer.Option(..., "--output", "-o", help="Output directory from a previous run (must contain report.json)."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Re-render the Markdown report and HTML dashboard from a saved report.json.

    Useful after template fixes or dashboard updates — no API calls required.

    Example:

        sea render --output ./output
    """
    _setup_logging(verbose)

    if not (output / "report.json").exists():
        console.print(f"[red]No report.json found in {output}[/]")
        console.print("Run [bold]sea analyze[/] first — it saves report.json at the end.")
        raise typer.Exit(code=1)

    asyncio.run(_run_render(output))


async def _run_render(out_dir: Path) -> None:
    """Re-render outputs from a saved report.json."""
    import json

    from sea.output.dashboard import render_dashboard
    from sea.output.markdown import render_markdown_report
    from sea.schemas.pipeline import FinalReport

    console.print(f"[bold]Loading report from:[/] {out_dir / 'report.json'}")
    report = FinalReport.model_validate_json((out_dir / "report.json").read_text())

    summary_path = out_dir / "executive-summary.txt"
    summary = summary_path.read_text() if summary_path.exists() else ""

    sc_paths_file = out_dir / "screenshot-paths.json"
    screenshot_paths = json.loads(sc_paths_file.read_text()) if sc_paths_file.exists() else None

    md_path = out_dir / "evolution-report.md"
    md_path.write_text(render_markdown_report(report, executive_summary=summary))
    console.print(f"[green]Markdown report written to:[/] {md_path}")

    html_path = out_dir / "evolution-dashboard.html"
    html_path.write_text(
        render_dashboard(report, executive_summary=summary, screenshot_paths=screenshot_paths)
    )
    console.print(f"[green]HTML dashboard written to:[/] {html_path}")


async def _run_feature_evaluation(
    cfg: "AnalysisConfig",  # noqa: F821
    features: list[str],
    *,
    dry_run: bool = False,
    patch_report: "Path | None" = None,  # noqa: F821
) -> None:
    """Run a focused pipeline: 4B (code analysis) + 4G (tech stack advisor)."""
    import json
    from pathlib import Path

    from sea.agents.code_analysis.agent import CodeAnalysisAgent
    from sea.agents.tech_stack_advisor.agent import TechStackAdvisorAgent
    from sea.shared.codebase_reader import CodebaseReader
    from sea.shared.progress import PipelineProgress

    if dry_run:
        from sea.shared.claude_client import DryRunClient
        client = DryRunClient()
    else:
        from sea.shared.claude_client import ClaudeClient
        client = ClaudeClient()

    reader = CodebaseReader(cfg.target_path)

    with PipelineProgress() as progress:
        # ── 4B Code Analysis ──────────────────────────────────────
        progress.print_phase("Analyzing codebase")
        progress.start_agent("4B Code Analysis")
        code_analysis = None
        try:
            agent_4b = CodeAnalysisAgent(client=client, reader=reader)
            user_msg = (
                f"Analyze the codebase at the root directory. "
                f"The user's priorities are: {', '.join(cfg.priorities)}"
            )
            code_analysis = await agent_4b.run(
                user_msg,
                on_progress=lambda m: progress.update_agent("4B Code Analysis", m),
                on_event=lambda m: progress.log_event("4B Code Analysis", m),
            )
            progress.finish_agent("4B Code Analysis")
        except Exception as exc:
            progress.fail_agent("4B Code Analysis", str(exc))

        # ── 4G Tech Stack Advisor ────────────────────────────────
        progress.print_phase("Tech Stack Evaluation")
        progress.start_agent("4G Tech Stack Advisor")
        try:
            agent_4g = TechStackAdvisorAgent(client=client, reader=reader)
            result = await agent_4g.run_evaluation(
                features=features,
                code_analysis=code_analysis,
                on_progress=lambda m: progress.update_agent("4G Tech Stack Advisor", m),
                on_event=lambda m: progress.log_event("4G Tech Stack Advisor", m),
            )
            progress.finish_agent("4G Tech Stack Advisor")
        except Exception as exc:
            progress.fail_agent("4G Tech Stack Advisor", str(exc))
            console.print(f"[red]Feature evaluation failed:[/] {exc}")
            return

    # ── Write output ────────────────────────────────────────────
    out_dir = Path(cfg.output_directory)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "feature-evaluation.json"
    out_path.write_text(json.dumps(result.model_dump(), indent=2))
    console.print(f"\n[green]Feature evaluation written to:[/] {out_path}")

    # Print a human-readable summary to stdout
    console.print("\n[bold]── Tech Stack Recommendations ──[/]\n")
    for feat in result.features:
        console.print(f"[bold cyan]{feat.feature_name}[/]")
        if feat.parity_source:
            console.print(f"  Competitors with this feature: {', '.join(feat.parity_source)}")
        console.print(f"  Current stack: {feat.current_stack_compatibility}")
        s = feat.simple_approach
        console.print(f"\n  [green]Simple:[/] {s.description}")
        console.print(f"    Stack: {', '.join(s.tech_stack)}")
        console.print(f"    Fit:   {s.architecture_fit}  |  Effort: {s.effort_estimate}")
        if feat.comprehensive_approach:
            c = feat.comprehensive_approach
            console.print(f"\n  [yellow]Comprehensive:[/] {c.description}")
            console.print(f"    Stack: {', '.join(c.tech_stack)}")
            console.print(f"    Fit:   {c.architecture_fit}  |  Effort: {c.effort_estimate}")
        console.print(f"\n  [bold]Recommended:[/] {feat.recommended_approach} — {feat.recommendation_rationale}")
        console.print("")

    # ── Patch report.json and re-render ─────────────────────────
    if patch_report:
        import json as _json
        from sea.output.dashboard import render_dashboard
        from sea.output.markdown import render_markdown_report
        from sea.schemas.pipeline import FinalReport

        report_path = patch_report / "report.json"
        report = FinalReport.model_validate_json(report_path.read_text())
        report.tech_stack_advisor = result
        report_path.write_text(report.model_dump_json(exclude={"screenshots"}, indent=2))
        console.print(f"[green]Patched:[/] {report_path}")

        summary_path = patch_report / "executive-summary.txt"
        summary = summary_path.read_text() if summary_path.exists() else ""

        sc_paths_file = patch_report / "screenshot-paths.json"
        screenshot_paths = _json.loads(sc_paths_file.read_text()) if sc_paths_file.exists() else None

        md_path = patch_report / "evolution-report.md"
        md_path.write_text(render_markdown_report(report, executive_summary=summary))
        console.print(f"[green]Markdown report written to:[/] {md_path}")

        html_path = patch_report / "evolution-dashboard.html"
        html_path.write_text(render_dashboard(report, executive_summary=summary, screenshot_paths=screenshot_paths))
        console.print(f"[green]HTML dashboard written to:[/] {html_path}")
