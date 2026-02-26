"""Orchestrator Agent — coordinates the two-pass pipeline."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from sea.agents.code_analysis.agent import CodeAnalysisAgent
from sea.agents.comparative_research.agent import ComparativeResearchAgent
from sea.agents.feature_recommender.agent import FeatureRecommenderAgent
from sea.agents.orchestrator.prompts import SYNTHESIS_SYSTEM_PROMPT
from sea.output.markdown import render_markdown_report
from sea.schemas.config import AnalysisConfig
from sea.schemas.pipeline import FinalReport, PipelineState, ScreenshotEntry
from sea.shared.browser import BrowserManager
from sea.shared.claude_client import ClaudeClient
from sea.shared.codebase_reader import CodebaseReader
from sea.shared.progress import PipelineProgress, console

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """Coordinates the multi-agent pipeline.

    Pipeline flow:
        4A + 4B (parallel) → 4C pass 1 → 4D + 4E (sequential) → 4C pass 2
        → 4F UX design audit → synthesis
    """

    def __init__(self, client: ClaudeClient, config: AnalysisConfig) -> None:
        self.client = client
        self.config = config
        self.state = PipelineState(config=config)

    # ------------------------------------------------------------------
    # Pre-flight checks
    # ------------------------------------------------------------------

    async def _check_url(self, url: str) -> None:
        """Quick HEAD request to verify a URL is reachable before starting.

        On failure, prompts the user to continue (codebase-only analysis)
        or abort.
        """
        import httpx
        from rich.prompt import Confirm

        console.print(f"[dim]Checking URL reachability: {url}[/]")
        problem: str | None = None

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15) as http:
                resp = await http.head(url)
                if resp.status_code >= 400:
                    problem = f"target URL returned HTTP {resp.status_code}"
                else:
                    console.print(f"[green]URL reachable[/] (HTTP {resp.status_code})")
                    return
        except httpx.ConnectError:
            problem = f"cannot connect to {url}"
        except httpx.TimeoutException:
            problem = f"{url} timed out after 15s"
        except Exception as exc:
            problem = f"could not verify {url}: {exc}"

        # URL has a problem — ask the user what to do
        console.print(f"\n[yellow]Warning:[/] {problem}")
        console.print(
            "[dim]Without a reachable URL, agents 4A (research) and 4E (quality audit) "
            "will be limited. The pipeline can still run using codebase analysis only.[/]"
        )

        try:
            proceed = Confirm.ask("[yellow]Continue without the target URL?[/]", default=False)
        except EOFError:
            proceed = False

        if not proceed:
            console.print("[red]Aborted.[/]")
            raise SystemExit(1)

        # User chose to continue — clear the URL so agents skip browser work
        console.print("[dim]Proceeding without target URL.[/]\n")
        self.config.target_url = ""

    def _check_path(self, path: str) -> None:
        """Verify the target codebase path exists."""
        p = Path(path)
        if not p.exists():
            console.print(f"[red]Error:[/] Target path does not exist: {path}")
            raise SystemExit(1)
        if not p.is_dir():
            console.print(f"[red]Error:[/] Target path is not a directory: {path}")
            raise SystemExit(1)
        console.print(f"[green]Codebase path verified[/]: {path}")

    async def run(self) -> FinalReport:
        """Execute the full pipeline and produce the final report."""

        # Pre-flight: verify targets are reachable before burning tokens
        if self.config.target_path:
            self._check_path(self.config.target_path)
        if self.config.target_url:
            await self._check_url(self.config.target_url)

        with PipelineProgress() as progress:
            # ── Pass 1: Research + Code Analysis (parallel) ──────
            progress.print_phase("Pass 1: Research + Code Analysis")

            await self._run_pass1(progress)

            # ── Screenshot all discovered sites in parallel ───────
            if self.config.target_url or self.state.research:
                progress.print_phase("Capturing Screenshots")
                await self._take_screenshots_parallel(progress)

            # ── 4C Pass 1: Feature Ranking ────────────────────────
            progress.print_phase("Feature Ranking (Pass 1)")

            await self._run_feature_ranking_pass1(progress)

            # ── Pass 2: Feasibility + Quality + Tech Stack ────────
            if self.state.pass1:
                progress.print_phase("Pass 2: Feasibility, Quality Audit & Tech Stack")
                await self._run_pass2(progress)

                # ── 4C Pass 2: Re-ranking ────────────────────────
                progress.print_phase("Feature Re-ranking (Pass 2)")
                await self._run_feature_ranking_pass2(progress)

            # ── 4F UX Design Audit ────────────────────────────────
            if self.state.screenshots:
                progress.print_phase("UX Design Audit")
                await self._run_ux_design_audit(progress)

            # ── Generate output ──────────────────────────────────
            progress.print_phase("Generating Report")

        report = self._build_report()
        await self._write_outputs(report)
        return report

    # ------------------------------------------------------------------
    # Pass 1
    # ------------------------------------------------------------------

    async def _run_pass1(self, progress: PipelineProgress) -> None:
        """Run 4A (Comparative Research) and 4B (Code Analysis) in parallel."""
        tasks = []

        # 4B always runs if we have a codebase path
        if self.config.target_path:
            progress.start_agent("4B Code Analysis")
            tasks.append(self._run_code_analysis(progress))

        # 4A runs if we have a URL or path (to derive the site's purpose)
        if self.config.target_url or self.config.target_path:
            progress.start_agent("4A Comparative Research")
            tasks.append(self._run_research(progress))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_code_analysis(self, progress: PipelineProgress) -> None:
        reader = CodebaseReader(self.config.target_path)
        agent = CodeAnalysisAgent(client=self.client, reader=reader)

        progress.log_event("4B Code Analysis", f"Codebase: [dim]{self.config.target_path}[/]")

        def on_progress(msg: str) -> None:
            progress.update_agent("4B Code Analysis", msg)

        def on_event(msg: str) -> None:
            progress.log_event("4B Code Analysis", msg)

        def on_tokens(inp: int, out: int) -> None:
            progress.record_tokens("4B Code Analysis", inp, out)

        try:
            user_msg = (
                f"Analyze the codebase at the root directory. "
                f"The user's priorities are: {', '.join(self.config.priorities)}"
            )
            self.state.code_analysis = await agent.run(
                user_msg, on_progress=on_progress, on_event=on_event, on_tokens=on_tokens,
            )
            progress.finish_agent("4B Code Analysis")
        except Exception as exc:
            logger.exception("4B Code Analysis failed")
            progress.fail_agent("4B Code Analysis", str(exc))

    async def _run_research(self, progress: PipelineProgress) -> None:
        async with BrowserManager() as browser:
            agent = ComparativeResearchAgent(client=self.client, browser=browser, site_depth=self.config.site_depth)

            if self.config.target_url:
                progress.log_event("4A Comparative Research", f"Target URL: [dim]{self.config.target_url}[/]")
            if self.config.competitor_urls:
                progress.log_event(
                    "4A Comparative Research",
                    f"Known competitors: [dim]{', '.join(self.config.competitor_urls)}[/]",
                )

            def on_progress(msg: str) -> None:
                progress.update_agent("4A Comparative Research", msg)

            def on_event(msg: str) -> None:
                progress.log_event("4A Comparative Research", msg)

            def on_tokens(inp: int, out: int) -> None:
                progress.record_tokens("4A Comparative Research", inp, out)

            try:
                parts = []
                if self.config.target_url:
                    parts.append(f"Target URL: {self.config.target_url}")
                if self.config.target_path:
                    parts.append(f"Target codebase: {self.config.target_path}")
                if self.config.site_name:
                    parts.append(f"Site name: {self.config.site_name}")
                if self.config.site_description:
                    parts.append(f"Site description: {self.config.site_description}")
                if self.config.competitor_urls:
                    parts.append(f"Known competitors: {', '.join(self.config.competitor_urls)}")
                parts.append(f"Target audience: All audiences")
                parts.append(f"Priorities: {', '.join(self.config.priorities)}")
                parts.append(f"site_depth: {self.config.site_depth}")

                user_msg = "\n".join(parts)
                self.state.research = await agent.run(
                    user_msg, on_progress=on_progress, on_event=on_event, on_tokens=on_tokens,
                )
                # Log discovered competitors after 4A completes
                if self.state.research and self.state.research.competitors:
                    comp_names = ", ".join(c.name for c in self.state.research.competitors[:6])
                    progress.log_event(
                        "4A Comparative Research",
                        f"Competitors found: [dim]{comp_names}[/]",
                    )
                progress.finish_agent("4A Comparative Research")
            except Exception as exc:
                logger.exception("4A Comparative Research failed")
                progress.fail_agent("4A Comparative Research", str(exc))

    # ------------------------------------------------------------------
    # Parallel screenshot capture
    # ------------------------------------------------------------------

    _MAX_SCREENSHOTS = 6  # target + up to 5 competitors

    async def _take_screenshots_parallel(self, progress: PipelineProgress) -> None:
        """Screenshot the target site and all discovered competitors in parallel.

        Runs after 4A completes so we have the full competitor URL list.
        Each URL gets its own Playwright page (concurrent via asyncio.gather).
        """
        urls: list[str] = []
        if self.config.target_url:
            urls.append(self.config.target_url)
        if self.state.research:
            for comp in self.state.research.competitors:
                if comp.url and comp.url not in urls:
                    urls.append(comp.url)

        urls = urls[: self._MAX_SCREENSHOTS]
        if not urls:
            return

        progress.log_event(
            "Screenshots",
            f"[dim]Taking {len(urls)} screenshot(s) in parallel: {', '.join(urls)}[/]",
        )

        async with BrowserManager() as browser:
            async def _shoot(url: str) -> None:
                try:
                    await browser.take_screenshot(url)
                    progress.log_event("Screenshots", f"[green]✓[/] {url}")
                except Exception as exc:
                    progress.log_event(
                        "Screenshots", f"[yellow]Screenshot failed for {url}: {exc}[/]"
                    )

            await asyncio.gather(*(_shoot(url) for url in urls))

            if browser.captured_screenshots:
                self.state.screenshots.extend(
                    ScreenshotEntry(**s) for s in browser.captured_screenshots
                )
                progress.log_event(
                    "Screenshots",
                    f"[green]Captured {len(browser.captured_screenshots)} screenshot(s)[/]",
                )

    # ------------------------------------------------------------------
    # 4C Pass 1
    # ------------------------------------------------------------------

    async def _run_feature_ranking_pass1(self, progress: PipelineProgress) -> None:
        if not self.state.research and not self.state.code_analysis:
            console.print("[yellow]Skipping 4C — no input data from Pass 1.[/]")
            return

        progress.start_agent("4C Feature Recommender (Pass 1)")
        agent = FeatureRecommenderAgent(client=self.client)

        def on_tokens_4c1(inp: int, out: int) -> None:
            progress.record_tokens("4C Feature Recommender (Pass 1)", inp, out)

        try:
            # Provide empty defaults if one agent failed
            from sea.schemas.research import ComparativeResearchOutput
            from sea.schemas.code_analysis import CodeAnalysisOutput

            research = self.state.research or ComparativeResearchOutput(competitors=[])
            code_analysis = self.state.code_analysis or CodeAnalysisOutput(tech_stack=[], architecture={})

            self.state.pass1 = await agent.run_pass1(
                research=research,
                code_analysis=code_analysis,
                priorities=self.config.priorities,
                on_tokens=on_tokens_4c1,
            )
            progress.finish_agent("4C Feature Recommender (Pass 1)")
        except Exception as exc:
            logger.exception("4C Pass 1 failed")
            progress.fail_agent("4C Feature Recommender (Pass 1)", str(exc))

    # ------------------------------------------------------------------
    # Pass 2
    # ------------------------------------------------------------------

    async def _run_pass2(self, progress: PipelineProgress) -> None:
        """Run 4D → 4G sequentially.

        Running these in parallel triggers OpenAI TPM rate limits on
        most org tiers, so we run them one at a time.
        """
        progress.start_agent("4D Tech Feasibility")
        await self._run_feasibility(progress)

        # 4E Quality Audit is temporarily disabled
        # if self.config.target_url:
        #     progress.start_agent("4E Quality Audit")
        #     await self._run_quality_audit(progress)

        if self.config.target_path:
            progress.start_agent("4G Tech Stack Advisor")
            await self._run_tech_stack_advisor(progress)

    async def _run_feasibility(self, progress: PipelineProgress) -> None:
        from sea.agents.tech_feasibility.agent import TechFeasibilityAgent

        if not self.config.target_path:
            progress.fail_agent("4D Tech Feasibility", "No codebase path")
            return

        reader = CodebaseReader(self.config.target_path)
        agent = TechFeasibilityAgent(client=self.client, reader=reader)

        def on_progress(msg: str) -> None:
            progress.update_agent("4D Tech Feasibility", msg)

        def on_event(msg: str) -> None:
            progress.log_event("4D Tech Feasibility", msg)

        def on_tokens(inp: int, out: int) -> None:
            progress.record_tokens("4D Tech Feasibility", inp, out)

        try:
            self.state.feasibility = await agent.run_assessment(
                pass1=self.state.pass1,
                code_analysis=self.state.code_analysis,
                constraints=self.config.constraints,
                on_progress=on_progress,
                on_event=on_event,
                on_tokens=on_tokens,
            )
            progress.finish_agent("4D Tech Feasibility")
        except Exception as exc:
            logger.exception("4D Tech Feasibility failed")
            progress.fail_agent("4D Tech Feasibility", str(exc))

    async def _run_quality_audit(self, progress: PipelineProgress) -> None:
        from sea.agents.quality_audit.agent import QualityAuditAgent

        async with BrowserManager() as browser:
            reader = CodebaseReader(self.config.target_path) if self.config.target_path else None
            agent = QualityAuditAgent(client=self.client, browser=browser, reader=reader)

            def on_progress(msg: str) -> None:
                progress.update_agent("4E Quality Audit", msg)

            def on_event(msg: str) -> None:
                progress.log_event("4E Quality Audit", msg)

            try:
                self.state.quality_audit = await agent.run_audit(
                    url=self.config.target_url,
                    code_analysis=self.state.code_analysis,
                    on_progress=on_progress,
                    on_event=on_event,
                )
                progress.finish_agent("4E Quality Audit")
            except Exception as exc:
                logger.exception("4E Quality Audit failed")
                progress.fail_agent("4E Quality Audit", str(exc))
            finally:
                if browser.captured_screenshots:
                    self.state.screenshots.extend(
                        ScreenshotEntry(**s) for s in browser.captured_screenshots
                    )
                    urls = [s["url"] for s in browser.captured_screenshots]
                    progress.log_event(
                        "4E Quality Audit",
                        f"[green]Captured {len(urls)} screenshot(s):[/] {', '.join(urls)}",
                    )

    async def _run_tech_stack_advisor(self, progress: PipelineProgress) -> None:
        from sea.agents.tech_stack_advisor.agent import TechStackAdvisorAgent

        if not self.config.target_path:
            progress.fail_agent("4G Tech Stack Advisor", "No codebase path")
            return

        # Determine which features to evaluate:
        # Start with explicit features from config, then add ALL 4C Pass 1
        # recommendations that aren't already covered (not just parity gaps —
        # any recommended feature may benefit from tech stack guidance).
        # Deduplication is case-insensitive exact match — the model handles
        # near-duplicates (e.g. "search" vs "Add site search") gracefully.
        features: list[str] = list(self.config.features)

        if self.state.pass1:
            seen = {f.lower() for f in features}
            for rec in self.state.pass1.recommendations:
                if rec.title.lower() not in seen:
                    features.append(rec.title)
                    seen.add(rec.title.lower())

        if not features:
            progress.finish_agent("4G Tech Stack Advisor")
            return

        reader = CodebaseReader(self.config.target_path)
        agent = TechStackAdvisorAgent(client=self.client, reader=reader)

        def on_progress(msg: str) -> None:
            progress.update_agent("4G Tech Stack Advisor", msg)

        def on_event(msg: str) -> None:
            progress.log_event("4G Tech Stack Advisor", msg)

        def on_tokens(inp: int, out: int) -> None:
            progress.record_tokens("4G Tech Stack Advisor", inp, out)

        try:
            self.state.tech_stack_advisor = await agent.run_evaluation(
                features=features,
                code_analysis=self.state.code_analysis,
                pass1=self.state.pass1,
                on_progress=on_progress,
                on_event=on_event,
                on_tokens=on_tokens,
            )
            progress.finish_agent("4G Tech Stack Advisor")
        except Exception as exc:
            logger.exception("4G Tech Stack Advisor failed")
            progress.fail_agent("4G Tech Stack Advisor", str(exc))

    # ------------------------------------------------------------------
    # 4C Pass 2
    # ------------------------------------------------------------------

    async def _run_feature_ranking_pass2(self, progress: PipelineProgress) -> None:
        if not self.state.pass1:
            return

        # Need at least one of feasibility or quality
        from sea.schemas.feasibility import FeasibilityOutput
        from sea.schemas.quality import QualityAuditOutput

        feasibility = self.state.feasibility or FeasibilityOutput(assessments=[])
        quality = self.state.quality_audit or QualityAuditOutput()

        progress.start_agent("4C Feature Recommender (Pass 2)")
        agent = FeatureRecommenderAgent(client=self.client)

        def on_tokens_4c2(inp: int, out: int) -> None:
            progress.record_tokens("4C Feature Recommender (Pass 2)", inp, out)

        try:
            self.state.pass2 = await agent.run_pass2(
                pass1=self.state.pass1,
                feasibility=feasibility,
                quality_audit=quality,
                on_tokens=on_tokens_4c2,
            )
            progress.finish_agent("4C Feature Recommender (Pass 2)")
        except Exception as exc:
            logger.exception("4C Pass 2 failed")
            progress.fail_agent("4C Feature Recommender (Pass 2)", str(exc))

    # ------------------------------------------------------------------
    # 4F UX Design Audit
    # ------------------------------------------------------------------

    async def _run_ux_design_audit(self, progress: PipelineProgress) -> None:
        from sea.agents.ux_design.agent import UXDesignAgent

        progress.start_agent("4F UX Design Audit")
        agent = UXDesignAgent(client=self.client)

        def on_progress(msg: str) -> None:
            progress.update_agent("4F UX Design Audit", msg)

        def on_event(msg: str) -> None:
            progress.log_event("4F UX Design Audit", msg)

        def on_tokens(inp: int, out: int) -> None:
            progress.record_tokens("4F UX Design Audit", inp, out)

        try:
            # Gather context from prior agents
            research_summary = ""
            if self.state.research and self.state.research.summary:
                research_summary = self.state.research.summary

            code_analysis_summary = ""
            design_system_info = ""
            if self.state.code_analysis:
                code_analysis_summary = self.state.code_analysis.summary or ""
                ds = self.state.code_analysis.design_system
                if ds:
                    design_system_info = (
                        f"Has design system: {ds.has_design_system}, "
                        f"Theming: {ds.theming_support}, "
                        f"Component library: {ds.component_library}"
                    )

            quality_summary = ""
            if self.state.quality_audit and self.state.quality_audit.summary:
                quality_summary = self.state.quality_audit.summary

            screenshots = [s.model_dump() for s in self.state.screenshots]

            self.state.ux_design = await agent.run_audit(
                screenshots,
                research_summary=research_summary,
                code_analysis_summary=code_analysis_summary,
                quality_summary=quality_summary,
                design_system_info=design_system_info,
                on_progress=on_progress,
                on_event=on_event,
                on_tokens=on_tokens,
            )
            progress.finish_agent("4F UX Design Audit")
        except Exception as exc:
            logger.exception("4F UX Design Audit failed")
            progress.fail_agent("4F UX Design Audit", str(exc))

    # ------------------------------------------------------------------
    # Output generation
    # ------------------------------------------------------------------

    def _build_report(self) -> FinalReport:
        feasibility = self.state.feasibility

        # After Pass 2 re-ranking, recommendation IDs are reassigned by new
        # rank (e.g. old REC-003 may become new REC-001).  Feasibility
        # assessments still reference the original Pass 1 IDs, so we remap
        # them to match the final recommendation IDs using title matching.
        if self.state.pass2 and self.state.pass1 and feasibility:
            feasibility = self._remap_feasibility_ids(feasibility)

        return FinalReport(
            config=self.config,
            research=self.state.research,
            code_analysis=self.state.code_analysis,
            recommendations=self.state.pass2 or self.state.pass1,
            feasibility=feasibility,
            quality_audit=self.state.quality_audit,
            tech_stack_advisor=self.state.tech_stack_advisor,
            ux_design=self.state.ux_design,
            screenshots=self.state.screenshots,
        )

    def _remap_feasibility_ids(self, feasibility: Any) -> Any:
        """Remap feasibility assessment IDs from Pass 1 to Pass 2 ordering.

        Builds a mapping from old IDs to new IDs by matching recommendation
        titles between Pass 1 and Pass 2, then updates each assessment.
        """
        from sea.schemas.feasibility import FeasibilityOutput

        # Build old_id → title from Pass 1
        old_id_to_title: dict[str, str] = {}
        for rec in self.state.pass1.recommendations:
            old_id_to_title[rec.id] = rec.title

        # Build title → new_id from Pass 2
        title_to_new_id: dict[str, str] = {}
        for rec in self.state.pass2.recommendations:
            title_to_new_id[rec.title] = rec.id

        # Build old_id → new_id
        id_map: dict[str, str] = {}
        for old_id, title in old_id_to_title.items():
            if title in title_to_new_id:
                id_map[old_id] = title_to_new_id[title]

        if not id_map:
            logger.warning("Could not build ID mapping between Pass 1 and Pass 2")
            return feasibility

        # Create remapped assessments sorted by new ID
        remapped = []
        for a in feasibility.assessments:
            new_id = id_map.get(a.recommendation_id, a.recommendation_id)
            remapped.append(a.model_copy(update={"recommendation_id": new_id}))
        remapped.sort(key=lambda a: a.recommendation_id)

        return FeasibilityOutput(
            assessments=remapped,
            summary=feasibility.summary,
        )

    async def _write_outputs(self, report: FinalReport) -> None:
        out_dir = Path(self.config.output_directory)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Save screenshots to disk
        screenshot_paths = self._save_screenshots(out_dir, report)

        # Generate executive summary
        summary = await self._generate_synthesis(report)

        # Markdown report
        md_path = out_dir / "evolution-report.md"
        md_content = render_markdown_report(report, executive_summary=summary)
        md_path.write_text(md_content)
        console.print(f"\n[green]Markdown report written to:[/] {md_path}")

        # HTML dashboard (Phase 6)
        try:
            from sea.output.dashboard import render_dashboard

            html_path = out_dir / "evolution-dashboard.html"
            html_content = render_dashboard(
                report, executive_summary=summary,
                screenshot_paths=screenshot_paths,
            )
            html_path.write_text(html_content)
            console.print(f"[green]HTML dashboard written to:[/] {html_path}")
        except ImportError:
            logger.debug("Dashboard module not yet available, skipping HTML output")

        # Save raw data for re-rendering without re-running agents
        import json as _json

        report_json_path = out_dir / "report.json"
        report_json_path.write_text(
            report.model_dump_json(exclude={"screenshots"}, indent=2)
        )
        (out_dir / "executive-summary.txt").write_text(summary)
        if screenshot_paths:
            (out_dir / "screenshot-paths.json").write_text(
                _json.dumps(screenshot_paths, indent=2)
            )
        console.print(f"[green]Report data saved to:[/] {report_json_path}  (use [bold]sea render[/] to re-render)")

    def _save_screenshots(
        self, out_dir: Path, report: FinalReport,
    ) -> list[dict[str, Any]]:
        """Write screenshot tiles to disk as JPEG files.

        Returns a list of dicts with ``url`` and ``tile_paths`` (relative to
        out_dir) for the dashboard template to reference.
        """
        import base64
        import re

        if not report.screenshots:
            return []

        screenshots_dir = out_dir / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)

        result: list[dict[str, Any]] = []
        for entry in report.screenshots:
            # Sanitize URL into a filesystem-safe prefix
            slug = re.sub(r"[^a-zA-Z0-9]+", "_", entry.url).strip("_")[:80]
            tile_paths: list[str] = []
            for i, tile_b64 in enumerate(entry.tiles):
                filename = f"{slug}_{i+1}.jpg"
                filepath = screenshots_dir / filename
                filepath.write_bytes(base64.b64decode(tile_b64))
                tile_paths.append(f"screenshots/{filename}")

            # Save full-page image for the dashboard
            full_page_path = ""
            if entry.full_page:
                full_filename = f"{slug}_full.jpg"
                (screenshots_dir / full_filename).write_bytes(
                    base64.b64decode(entry.full_page)
                )
                full_page_path = f"screenshots/{full_filename}"

            result.append({
                "url": entry.url,
                "tile_paths": tile_paths,
                "full_page_path": full_page_path,
            })

        total_files = sum(len(r["tile_paths"]) for r in result)
        console.print(
            f"[green]Screenshots saved to:[/] {screenshots_dir}/ "
            f"({total_files} files across {len(result)} sites)"
        )
        return result

    async def _generate_synthesis(self, report: FinalReport) -> str:
        """Ask Claude for a final executive summary.

        Builds a slim payload with only the fields the synthesis prompt
        needs, avoiding sending the full 100-500 KB FinalReport.
        """
        import json

        try:
            slim: dict = {}

            if report.recommendations:
                recs = report.recommendations.model_dump()
                slim["recommendations"] = [
                    {
                        "id": r["id"],
                        "title": r["title"],
                        "category": r["category"],
                        "rank": r.get("rank"),
                        "scores": r.get("scores"),
                    }
                    for r in recs.get("recommendations", [])
                ]
                slim["quick_wins"] = recs.get("quick_wins", [])
                slim["summary"] = recs.get("summary", "")

            if report.feasibility:
                f = report.feasibility
                slim["feasibility_summary"] = f.summary if hasattr(f, "summary") else ""

            if report.quality_audit:
                q = report.quality_audit
                slim["quality_summary"] = q.summary if hasattr(q, "summary") else ""

            if report.research:
                r = report.research
                slim["research_summary"] = r.summary if hasattr(r, "summary") else ""

            if report.code_analysis:
                c = report.code_analysis
                slim["code_summary"] = c.summary if hasattr(c, "summary") else ""

            if report.ux_design:
                u = report.ux_design
                slim["ux_design_summary"] = u.summary if hasattr(u, "summary") else ""

            return await self.client.simple_completion(
                system=SYNTHESIS_SYSTEM_PROMPT,
                user_message=json.dumps(slim, default=str),
                json_mode=False,
            )
        except Exception:
            logger.warning("Failed to generate synthesis, using fallback")
            return "Executive summary generation failed. See individual sections below."
