"""Exploration engine — state machine loop that orchestrates the agent."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from rich.console import Console
from rich.panel import Panel

from src.config import AppConfig
from src.agent.state import (
    AgentPhase, AgentState, ExplorationTarget, StateSnapshot,
    ActionType, TargetType, VisitStatus, PageCoverage,
)
from src.agent.logger import RunLogger
from src.browser.controller import BrowserController
from src.browser.authenticator import Authenticator
from src.observer.extractor import CandidateExtractor
from src.observer.fingerprint import DOMFingerprinter
from src.observer.novelty import NoveltyScorer
from src.analyzer.page_analyzer import PageAnalyzer
from src.analysis.competitive_report import CompetitiveReportGenerator
from src.artifacts.manager import ArtifactManager
from src.artifacts.inventory import InventoryGenerator
from src.artifacts.sitemap import SitemapGenerator
from src.artifacts.report import ReportGenerator
from src.extraction.engine import ExtractionEngine
from src.extraction.types import EvidencePaths
from src.vision.client import VisionClient
from src.vision.types import DOMSummary, PageInsight, VisionResult

console = Console()


class ExplorationEngine:
    """State machine engine for autonomous website exploration."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.state = AgentState(
            budget=config.budget.max_states,
            max_depth=config.budget.max_depth,
        )

        # Components
        self.controller = BrowserController(config)
        self.authenticator = Authenticator(config, self.controller)
        self.extractor = CandidateExtractor(config)
        self.fingerprinter = DOMFingerprinter()
        self.novelty_scorer = NoveltyScorer(self.fingerprinter)
        self.analyzer = PageAnalyzer()
        self.competitive = CompetitiveReportGenerator()
        self.artifacts = ArtifactManager(config)
        self.extraction = ExtractionEngine()
        self.vision = VisionClient(config.vision)

        # Logger (created lazily after output is cleared)
        self._logger: RunLogger | None = None
        self._log_path = Path(__file__).parent.parent.parent / config.output.artifacts_dir / "run_log.jsonl"

        # Analysis results (state_id -> analysis dict)
        self._analysis_results: dict[str, dict] = {}
        self._vision_results: dict[str, dict] = {}
        self._page_insights: dict[str, dict] = {}
        self._extraction_results: dict[str, dict] = {}

        # Timing
        self._start_time: str = ""

    @property
    def logger(self) -> RunLogger:
        if self._logger is None:
            self._logger = RunLogger(self._log_path)
        return self._logger

    async def run(self) -> AgentState:
        """Run the full exploration loop."""
        self._start_time = datetime.now().isoformat()

        console.print(Panel.fit(
            f"[bold cyan]Frontend Mimic Agent[/bold cyan]\n"
            f"Target: {self.config.target.url}\n"
            f"Budget: {self.config.budget.max_states} states, depth {self.config.budget.max_depth}\n"
            f"Novelty threshold: {self.config.budget.novelty_threshold}",
            title="Agent Configuration",
        ))

        try:
            # INITIALIZE
            await self._phase_initialize()

            # AUTHENTICATE
            await self._phase_authenticate()

            # Navigate to dashboard if configured
            dashboard_url = self.config.target.dashboard_url
            if dashboard_url:
                await self.controller.goto(dashboard_url)

            # Create initial target for the current page
            current_url = await self.controller.get_url()
            root_target = ExplorationTarget.create(
                target_type=TargetType.ROUTE,
                locator=current_url,
                label=self._url_to_label(current_url),
                depth=0,
                discovery_method="initial_page",
            )
            self.state.add_target(root_target)

            # Main exploration loop — frontier contains ONLY route targets
            while True:
                # OBSERVE current page (discover nav routes)
                await self._phase_observe()

                # SELECT next route from frontier
                target = self._phase_select_action()
                if target is None:
                    break

                # EXECUTE route navigation
                snapshot = await self._execute_route(target)
                if snapshot is None:
                    continue

                # ANALYZE the route page
                await self._phase_analyze(snapshot)
                await self._run_extraction(
                    snapshot,
                    capture_label=target.label or self._url_to_label(snapshot.url),
                    capture_context="route",
                    allow_vision=True,
                )

                # EXPLORE all interactions on this page (inline, no frontier)
                if self.state.has_budget():
                    await self._explore_page_interactions(target)

            # FINALIZE
            await self._phase_finalize()

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")
            await self._phase_finalize()
        except Exception as e:
            console.print(f"\n[red]Engine error: {e}[/red]")
            self.logger.log(AgentPhase.FINALIZE, "engine_error", "", "failed", str(e))
            await self._phase_finalize()
        finally:
            await self.controller.stop()
            if self._logger:
                self._logger.close()

        return self.state

    # ── Phase implementations ──

    async def _phase_initialize(self) -> None:
        """INITIALIZE: Launch browser, set up output dirs."""
        self.state.phase = AgentPhase.INITIALIZE
        self.artifacts.clear_output()

        with self.logger.timed(AgentPhase.INITIALIZE, "launch_browser") as ctx:
            await self.controller.start()
            ctx["reason"] = "chromium started"

        console.print("[green]Browser launched, output cleared[/green]")

    async def _phase_authenticate(self) -> None:
        """AUTHENTICATE: Login to target website with retries."""
        self.state.phase = AgentPhase.AUTHENTICATE

        for attempt in range(3):
            with self.logger.timed(AgentPhase.AUTHENTICATE, "login", self.config.target.url) as ctx:
                success = await self.authenticator.login()
                if success:
                    ctx["reason"] = "login successful"
                    console.print("[green]Authenticated successfully[/green]")
                    return
                ctx["result"] = "retry" if attempt < 2 else "failed"
                ctx["reason"] = f"login attempt {attempt + 1} failed"
            console.print(f"[yellow]Login attempt {attempt + 1} failed, retrying...[/yellow]")
            await asyncio.sleep(3)

        raise RuntimeError("Authentication failed after 3 attempts. Check credentials in config.")

    async def _phase_observe(self) -> None:
        """OBSERVE: Extract route candidates from current page, add to frontier."""
        self.state.phase = AgentPhase.OBSERVE

        current_url = await self.controller.get_url()
        current_target = self.state.targets.get(self.state.current_target_id or "")
        current_depth = current_target.depth if current_target else 0

        # Skip re-observation of already-observed URLs
        normalized_url = self._normalize_url(current_url)
        if normalized_url in self.state.observed_urls:
            return
        self.state.observed_urls.add(normalized_url)

        with self.logger.timed(AgentPhase.OBSERVE, "extract_candidates",
                               current_target.label if current_target else "root") as ctx:
            candidates, coverage = await self.extractor.extract_all(
                self.controller.page, self.state.current_target_id, current_depth
            )
            dom_summary = await self._build_dom_summary()
            vision_result = await self._understand_current_page(current_url, dom_summary)
            route_candidates = self._rerank_route_candidates(
                [c for c in candidates if c.target_type == TargetType.ROUTE], vision_result
            )
            insight = self._build_page_insight(current_url, dom_summary, vision_result)
            self._persist_page_understanding(insight, vision_result)

            # Only add ROUTE targets to the frontier
            added = self.state.add_targets(route_candidates)
            ctx["reason"] = (
                f"found {len(route_candidates)} routes, {added} new, "
                f"page_type={insight.page_type_vision}"
            )

            if current_target and current_target.id not in self.state.coverage:
                self.state.coverage[current_target.id] = coverage

        if added > 0:
            console.print(f"[cyan]  Discovered {added} new routes (frontier: {len(self.state.frontier)})[/cyan]")

    def _phase_select_action(self) -> ExplorationTarget | None:
        """SELECT_ACTION: Pick next route from frontier, check budget."""
        self.state.phase = AgentPhase.SELECT_ACTION

        if not self.state.has_budget():
            self.logger.log(AgentPhase.SELECT_ACTION, "budget_exhausted", "", "success",
                          f"budget exhausted ({self.state.budget_total} states)")
            console.print("[yellow]Budget exhausted[/yellow]")
            return None

        target = self.state.pop_frontier()
        if target is None:
            self.logger.log(AgentPhase.SELECT_ACTION, "frontier_empty", "", "success",
                          "no more routes to explore")
            console.print("[yellow]Frontier empty — exploration complete[/yellow]")
            return None

        self.logger.log(AgentPhase.SELECT_ACTION, "selected_target", target.label, "success",
                      f"type={target.target_type.value}, depth={target.depth}")
        return target

    async def _execute_route(self, target: ExplorationTarget) -> StateSnapshot | None:
        """Navigate to a route and capture it. Routes are always captured."""
        step = self.state.next_step()
        console.print(f"\n[bold cyan]Step {step}: route → {target.label}[/bold cyan]")

        # Navigate
        success = False
        for attempt in range(1 + self.config.budget.retry_limit):
            with self.logger.timed(AgentPhase.EXECUTE, "navigate", target.label) as ctx:
                try:
                    success = await self._navigate_to_target(target)
                    if success:
                        ctx["reason"] = "navigation successful"
                        break
                    ctx["result"] = "retry" if attempt < self.config.budget.retry_limit else "failed"
                    ctx["reason"] = f"attempt {attempt + 1} failed"
                except Exception as e:
                    ctx["result"] = "retry" if attempt < self.config.budget.retry_limit else "failed"
                    ctx["reason"] = str(e)
            if not success and attempt < self.config.budget.retry_limit:
                await asyncio.sleep(1)

        if not success:
            self.state.mark_failed(target.id)
            return None

        # Check session
        if not await self.authenticator.check_session():
            await self.authenticator.re_login()
            return None

        # Routes are ALWAYS captured
        snapshot = await self._capture_and_register(target)
        return snapshot

    async def _explore_page_interactions(self, route_target: ExplorationTarget) -> None:
        """Explore all interactions on the current page inline (no frontier).

        Order: action dropdowns → dropdown items → add buttons → tabs → expand rows.
        Each capture goes through novelty check.
        """
        page = self.controller.page
        icfg = self.config.interaction
        wait = self.config.crawl.wait_after_navigation / 1000
        timeout = self.config.crawl.interaction_timeout
        max_items = self.config.crawl.max_interaction_items
        destructive = self.config.exploration.destructive_keywords
        strict_dd_selector = self.config.interaction.dropdown_item_strict_selector

        coverage = self.state.coverage.get(route_target.id, PageCoverage())
        route_label = route_target.label

        console.print(f"[yellow]  Exploring interactions on: {route_label}[/yellow]")

        # ── 1. Action dropdown → click each item ──
        action_loc, action_count = await self.controller.find_first_visible(icfg.action_button_selectors)
        if action_loc and action_count > 0:
            coverage.action_buttons_found = action_count
            console.print(f"[cyan]    Action buttons: {action_count} found[/cyan]")

            # Click first action button to open dropdown
            try:
                await self.controller.click_locator(action_loc.first, wait=0.8)
                coverage.action_buttons_clicked += 1

                # Capture the dropdown menu state
                await self._capture_interaction("action_dropdown", route_target, "dropdown")

                # Discover dropdown items
                items = page.locator(strict_dd_selector)
                item_count = await items.count()
                coverage.dropdown_items_found = item_count
                console.print(f"[cyan]    Dropdown items: {item_count} found[/cyan]")

                # Collect item texts first (before clicking anything)
                item_texts = []
                for i in range(min(item_count, max_items)):
                    try:
                        text = (await items.nth(i).text_content() or "").strip()
                        if text:
                            item_texts.append((i, text))
                    except Exception:
                        continue

                # Close the dropdown before clicking items
                await self.controller.close_overlays()

                # Now click each dropdown item
                for item_idx, item_text in item_texts:
                    if not self.state.has_budget():
                        break
                    if any(kw.lower() in item_text.lower() for kw in destructive):
                        console.print(f"[dim]    Skipping destructive: {item_text}[/dim]")
                        continue

                    coverage.dropdown_item_labels.append(item_text)
                    console.print(f"[cyan]    Clicking dropdown item: {item_text}[/cyan]")

                    # Re-open dropdown and click the item
                    try:
                        await self.controller.click_locator(action_loc.first, wait=0.5)
                        await asyncio.sleep(0.3)

                        # Re-find items (DOM may have changed)
                        fresh_items = page.locator(strict_dd_selector)
                        fresh_count = await fresh_items.count()
                        if item_idx >= fresh_count:
                            await self.controller.close_overlays()
                            continue

                        await fresh_items.nth(item_idx).click()
                        await asyncio.sleep(wait)

                        # Capture the result
                        label = f"{item_text}@{route_label}"
                        result = await self._capture_interaction(label, route_target, "dropdown_item")
                        if result == "captured":
                            coverage.dropdown_items_explored += 1
                        elif result == "skipped_novelty":
                            coverage.dropdown_items_skipped_novelty += 1

                        # Recover: close modal or go back
                        if await self.controller.is_modal_open():
                            await self.controller.close_overlays()
                        else:
                            # Might have navigated to a new page — go back
                            current_url = await self.controller.get_url()
                            if self._normalize_url(current_url) != self._normalize_url(
                                    await self._get_route_url(route_target)):
                                await self.controller.go_back()
                                await asyncio.sleep(wait)

                    except Exception as e:
                        console.print(f"[dim]    Failed: {item_text} ({e})[/dim]")
                        await self.controller.close_overlays()

            except Exception as e:
                console.print(f"[dim]    Action dropdown failed: {e}[/dim]")
                await self.controller.close_overlays()

        # ── 2. Add/create button → modal ──
        add_loc, _ = await self.controller.find_first_visible(icfg.add_button_selectors)
        if add_loc:
            coverage.add_buttons_found += 1
            try:
                add_text = (await add_loc.first.text_content() or "add").strip()
                console.print(f"[cyan]    Add button: {add_text}[/cyan]")
                await self.controller.click_locator(add_loc.first, wait=wait)

                label = f"add_form_{add_text}@{route_label}"
                result = await self._capture_interaction(label, route_target, "modal")
                if result == "captured":
                    coverage.add_buttons_clicked += 1
                elif result == "skipped_novelty":
                    coverage.add_buttons_skipped_novelty += 1

                await self.controller.close_overlays()
            except Exception as e:
                console.print(f"[dim]    Add button failed: {e}[/dim]")
                await self.controller.close_overlays()

        # ── 3. Expandable rows ──
        expand_loc, expand_count = await self.controller.find_first_visible(icfg.expand_selectors)
        if expand_loc and expand_count > 0:
            coverage.expand_rows_found = expand_count
            try:
                console.print(f"[cyan]    Expandable rows: {expand_count} found[/cyan]")
                await self.controller.click_locator(expand_loc.first, wait=1.0)

                label = f"expand_row@{route_label}"
                result = await self._capture_interaction(label, route_target, "expanded_row")
                if result == "captured":
                    coverage.expand_rows_expanded += 1
                elif result == "skipped_novelty":
                    coverage.expand_rows_skipped_novelty += 1
            except Exception:
                pass

        # ── 4. Tabs ──
        try:
            tabs = page.locator(icfg.tab_selector)
            tab_count = await tabs.count()
            if tab_count > 0:
                coverage.tabs_found = tab_count
                console.print(f"[cyan]    Tabs: {tab_count} found[/cyan]")
                for i in range(min(tab_count, 4)):
                    if not self.state.has_budget():
                        break
                    try:
                        tab = tabs.nth(i)
                        if not await tab.is_visible():
                            continue
                        tab_text = (await tab.text_content() or "").strip()
                        if not tab_text:
                            continue
                        coverage.tab_labels.append(tab_text)

                        console.print(f"[cyan]    Switching tab: {tab_text}[/cyan]")
                        await tab.click()
                        await asyncio.sleep(wait)

                        label = f"tab_{tab_text}@{route_label}"
                        result = await self._capture_interaction(label, route_target, "tab_state")
                        if result == "captured":
                            coverage.tabs_switched += 1
                        elif result == "skipped_novelty":
                            coverage.tabs_skipped_novelty += 1
                    except Exception:
                        continue
        except Exception:
            pass

        # Update coverage
        if route_target.id in self.state.coverage:
            self.state.coverage[route_target.id] = coverage

    async def _capture_interaction(self, label: str, parent_target: ExplorationTarget,
                                    context: str) -> str:
        """Capture an interaction state with novelty check.
        Returns: 'captured', 'skipped_novelty', or 'skipped_budget'."""
        if not self.state.has_budget():
            return "skipped_budget"

        # Novelty check
        html = await self.controller.get_html()
        novelty, fingerprint = self.novelty_scorer.score(html)
        threshold = self.config.budget.novelty_threshold

        if novelty < threshold:
            self.novelty_scorer.register(html, fingerprint)
            console.print(f"[dim]    Low novelty ({novelty:.2f}) — skipped[/dim]")
            self.logger.log(AgentPhase.EVAL_NOVELTY, "skip_interaction", label,
                          "skipped", f"novelty={novelty:.2f}")
            return "skipped_novelty"

        # Capture
        url = await self.controller.get_url()
        title = await self.controller.get_title()
        screenshot_path = await self.controller.capture_screenshot(label, context)
        html_path = await self.controller.save_html(label, context)

        snapshot = StateSnapshot.create(
            target_id=parent_target.id,
            url=url, title=title,
            screenshot_path=screenshot_path, html_path=html_path,
            visit_status=VisitStatus.SUCCESS,
            depth=parent_target.depth + 1,
            novelty_score=novelty, dom_fingerprint=fingerprint,
        )
        self.state.register_state(snapshot)
        self.state.consume_budget()
        self.novelty_scorer.register(html, fingerprint)

        # Analyze
        computed_styles = await self.controller.get_computed_styles()
        analysis = self.analyzer.analyze(html, computed_styles)
        self._analysis_results[snapshot.id] = analysis
        self.artifacts.save_analysis(snapshot.id, analysis)
        await self._run_extraction(
            snapshot,
            capture_label=label,
            capture_context=context,
            allow_vision=False,
        )

        self.logger.log(AgentPhase.EXECUTE, f"capture_{context}", label,
                      "success", f"novelty={novelty:.2f}")
        console.print(f"[green]    Captured: {url} (novelty={novelty:.2f})[/green]")
        return "captured"

    async def _phase_analyze(self, snapshot: StateSnapshot) -> None:
        """ANALYZE: Run local page analysis on the captured state."""
        self.state.phase = AgentPhase.ANALYZE

        html = ""
        try:
            html_path = Path(snapshot.html_path)
            if html_path.exists():
                html = html_path.read_text(encoding="utf-8")
        except Exception:
            return

        if not html:
            return

        with self.logger.timed(AgentPhase.ANALYZE, "analyze_page", snapshot.id) as ctx:
            computed_styles = await self.controller.get_computed_styles()
            analysis = self.analyzer.analyze(html, computed_styles)
            self._analysis_results[snapshot.id] = analysis
            self.artifacts.save_analysis(snapshot.id, analysis)
            ctx["reason"] = f"components: {', '.join(analysis.get('component_types', []))}"

    async def _run_extraction(
        self,
        snapshot: StateSnapshot,
        capture_label: str = "",
        capture_context: str = "",
        allow_vision: bool = True,
    ) -> None:
        """Run structured extraction for a captured route page."""
        html = ""
        try:
            html_path = Path(snapshot.html_path)
            if html_path.exists():
                html = html_path.read_text(encoding="utf-8")
        except Exception:
            html = ""

        if not html:
            return

        if snapshot.id not in self._page_insights:
            dom_summary = await self._build_dom_summary()
            vision_result = (
                await self._understand_current_page(snapshot.url, dom_summary)
                if allow_vision else VisionResult()
            )
            insight_obj = self._build_page_insight(
                snapshot.url,
                dom_summary,
                vision_result,
                state_id=snapshot.id,
            )
            self._persist_page_understanding(insight_obj, vision_result)

        insight = self._page_insights.get(snapshot.id) or {}
        strategy = str(insight.get("extraction_strategy", "unknown"))
        page_type = self._resolved_page_type(insight)

        evidence_paths = EvidencePaths(
            screenshot=snapshot.screenshot_path,
            html=snapshot.html_path,
        )

        result = self.extraction.extract(
            html=html,
            state_id=snapshot.id,
            target_id=snapshot.target_id,
            url=snapshot.url,
            page_type=page_type,
            strategy=strategy,
            evidence_paths=evidence_paths,
        )
        result.capture_label = capture_label
        result.capture_context = capture_context
        self._extraction_results[snapshot.id] = result.model_dump()

    async def _phase_finalize(self) -> None:
        """FINALIZE: Generate all artifacts and report."""
        self.state.phase = AgentPhase.FINALIZE
        end_time = datetime.now().isoformat()

        console.print("\n[bold]Generating artifacts...[/bold]")

        with self.logger.timed(AgentPhase.FINALIZE, "generate_inventory") as ctx:
            inventory = InventoryGenerator().generate(self.state)
            path = self.artifacts.save_json("inventory.json", inventory)
            ctx["reason"] = f"{len(inventory)} entries → {path.name}"

        with self.logger.timed(AgentPhase.FINALIZE, "generate_sitemap") as ctx:
            sitemap = SitemapGenerator().generate(self.state)
            path = self.artifacts.save_json("sitemap.json", sitemap)
            ctx["reason"] = f"{sitemap['stats']['total_nodes']} nodes → {path.name}"

        with self.logger.timed(AgentPhase.FINALIZE, "generate_coverage") as ctx:
            from dataclasses import asdict
            coverage_data = {tid: asdict(cov) for tid, cov in self.state.coverage.items()}
            path = self.artifacts.save_json("coverage.json", coverage_data)
            pages_with_gaps = sum(1 for c in self.state.coverage.values() if c.has_unexplored)
            ctx["reason"] = f"{len(coverage_data)} pages, {pages_with_gaps} with gaps → {path.name}"

        with self.logger.timed(AgentPhase.FINALIZE, "generate_extraction_artifacts") as ctx:
            extraction_rows = list(self._extraction_results.values())
            summary = self._build_extraction_summary(extraction_rows)
            failures = [
                row for row in extraction_rows
                if row.get("status") in {"failed", "empty"} or row.get("error")
            ]
            self.artifacts.save_jsonl("dataset.jsonl", extraction_rows)
            self.artifacts.save_json("dataset_summary.json", summary)
            self.artifacts.save_json("extraction_failures.json", failures)
            ctx["reason"] = (
                f"{summary['total_results']} results, "
                f"{summary['successful_results']} successful"
            )

        with self.logger.timed(AgentPhase.FINALIZE, "generate_report") as ctx:
            report = ReportGenerator().generate(
                self.state,
                self._start_time,
                end_time,
                self._analysis_results,
                self._page_insights,
                self._extraction_results,
            )
            path = self.artifacts.save_text("exploration_report.md", report)
            ctx["reason"] = f"report → {path.name}"

        with self.logger.timed(AgentPhase.FINALIZE, "generate_competitive_analysis") as ctx:
            competitive = self.competitive.generate(
                self.state,
                self._analysis_results,
                self._page_insights,
                self._extraction_results,
            )
            self.artifacts.save_json("competitive_analysis.json", competitive.model_dump())
            self.artifacts.save_text(
                "competitive_analysis.md",
                self.competitive.generate_markdown(competitive),
            )
            ctx["reason"] = (
                f"category={competitive.competitive_summary.product_category_guess}, "
                f"modules={len(competitive.feature_modules)}"
            )

        stats = self.state.get_stats()
        console.print(Panel.fit(
            f"[bold green]Exploration Complete[/bold green]\n\n"
            f"States captured: {stats['states_captured']}\n"
            f"Targets discovered: {stats['total_targets']}\n"
            f"Visited: {stats['visited']} | Skipped: {stats['skipped']} | Failed: {stats['failed']}\n"
            f"Budget used: {stats['budget_used']} / {self.state.budget_total}\n"
            f"Steps: {stats['steps']}\n\n"
            f"Artifacts:\n"
            f"  inventory.json, sitemap.json, run_log.jsonl\n"
            f"  exploration_report.md\n"
            f"  {len(self._analysis_results)} state analyses\n"
            f"  {len(self._page_insights)} page insights\n"
            f"  {len(self._extraction_results)} extraction results\n"
            f"  competitive_analysis.json / .md",
            title="Summary",
        ))

    # ── Helpers ──

    async def _build_dom_summary(self) -> DOMSummary:
        """Build a lightweight DOM summary for vision understanding."""
        title = await self.controller.get_title()
        html = await self.controller.get_html()
        analysis = self.analyzer.analyze(html)

        return DOMSummary(
            title=title,
            component_types=analysis.get("component_types", []),
            nav_labels=await self._collect_visible_texts(self.config.exploration.nav_selectors, 8),
            button_labels=await self._collect_visible_texts(
                ["button", ".el-button", ".ant-btn", ".btn"], 10
            ),
            tab_labels=await self._collect_visible_texts([self.config.interaction.tab_selector], 6),
            table_headers=await self._collect_visible_texts(
                ["table th", ".el-table th", ".ant-table th"], 8
            ),
            has_modal=await self.controller.is_modal_open(),
            has_table=self._has_component(analysis, "table"),
            has_form=self._has_component(analysis, "form"),
            has_pagination=self._has_component(analysis, "pagination"),
        )

    async def _understand_current_page(self, current_url: str, dom_summary: DOMSummary) -> VisionResult:
        """Run vision understanding for the current page if enabled."""
        if not self.config.vision.enabled:
            return VisionResult()

        try:
            screenshot_path = await self.controller.capture_viewport_screenshot("vision_observe", "vision")
            return await self.vision.understand_page(screenshot_path, current_url, dom_summary)
        except Exception as e:
            self.logger.log(AgentPhase.OBSERVE, "vision_understanding", current_url, "failed", str(e))
            return VisionResult(notes=f"vision_failed: {e}")

    def _rerank_route_candidates(self, route_candidates: list[ExplorationTarget],
                                 vision_result: VisionResult) -> list[ExplorationTarget]:
        """Rerank route candidates using page-type hints without changing executability."""
        page_type = vision_result.page_type
        if page_type == "unknown" or not route_candidates:
            return route_candidates

        def score(candidate: ExplorationTarget) -> tuple[int, int, str]:
            label = candidate.label.lower()
            score_value = 0

            if page_type == "dashboard":
                if any(term in label for term in ["list", "manage", "admin", "setting", "config", "user"]):
                    score_value += 3
            elif page_type == "list":
                if any(term in label for term in ["detail", "view", "record", "item"]):
                    score_value += 2
                if any(term in label for term in ["report", "analytics", "dashboard"]):
                    score_value -= 1
            elif page_type == "detail":
                if any(term in label for term in ["detail", "view", "profile", "record"]):
                    score_value += 2
            elif page_type in {"form", "modal"}:
                if any(term in label for term in ["create", "new", "edit", "config", "setting"]):
                    score_value += 2

            return (-score_value, candidate.depth, candidate.label)

        return sorted(route_candidates, key=score)

    def _build_page_insight(self, current_url: str, dom_summary: DOMSummary,
                            vision_result: VisionResult, state_id: str | None = None) -> PageInsight:
        """Build a merged page insight from DOM and vision understanding."""
        insight_state_id = state_id or self.state.current_state_id or f"observe_{self._url_to_label(current_url)}"
        page_type_dom = self._infer_dom_page_type(dom_summary)

        return PageInsight(
            state_id=insight_state_id,
            url=current_url,
            page_type_dom=page_type_dom,
            page_type_vision=vision_result.page_type,
            dom_component_types=dom_summary.component_types,
            vision_regions=vision_result.regions,
            interaction_hints=vision_result.interaction_hints,
            extraction_strategy=self._choose_extraction_strategy(page_type_dom, vision_result.page_type),
            high_value_page=self._is_high_value_page(dom_summary, vision_result),
            analysis_tags=self._derive_analysis_tags(dom_summary, vision_result),
        )

    def _persist_page_understanding(self, insight: PageInsight, vision_result: VisionResult) -> None:
        """Persist page insight and optional vision output artifacts."""
        self._page_insights[insight.state_id] = insight.model_dump()
        self.artifacts.save_page_insight(insight.state_id, insight.model_dump())

        if self.config.vision.enabled:
            self._vision_results[insight.state_id] = vision_result.model_dump()
            self.artifacts.save_vision(insight.state_id, vision_result.model_dump())

    async def _collect_visible_texts(self, selectors: list[str], limit: int) -> list[str]:
        """Collect visible text snippets for a list of selectors."""
        texts: list[str] = []
        seen: set[str] = set()

        for selector in selectors:
            try:
                locator = self.controller.page.locator(selector)
                count = await locator.count()
                for i in range(min(count, limit)):
                    try:
                        item = locator.nth(i)
                        if not await item.is_visible():
                            continue
                        text = (await item.text_content() or "").strip()
                        if not text:
                            continue
                        compact = " ".join(text.split())
                        if len(compact) > 60:
                            compact = compact[:57] + "..."
                        if compact not in seen:
                            seen.add(compact)
                            texts.append(compact)
                        if len(texts) >= limit:
                            return texts
                    except Exception:
                        continue
            except Exception:
                continue

        return texts

    def _has_component(self, analysis: dict, component_name: str) -> bool:
        """Return True if a component type is present in analyzer output."""
        return component_name in analysis.get("component_types", [])

    def _infer_dom_page_type(self, summary: DOMSummary) -> str:
        """Infer a coarse page type from DOM summary only."""
        components = set(summary.component_types)
        if summary.has_modal:
            return "modal"
        if "table" in components:
            return "list"
        if "form" in components:
            return "form"
        if "tabs" in components and "table" not in components:
            return "detail"
        if "card" in components and "table" not in components and "form" not in components:
            return "dashboard"
        return "unknown"

    def _choose_extraction_strategy(self, page_type_dom: str, page_type_vision: str) -> str:
        """Choose the provisional extraction strategy for a page."""
        page_type = page_type_vision if page_type_vision != "unknown" else page_type_dom
        if page_type == "list":
            return "list_table"
        if page_type == "detail":
            return "detail_fields"
        if page_type in {"form", "modal"}:
            return "form_schema"
        return "unknown"

    def _is_high_value_page(self, summary: DOMSummary, vision_result: VisionResult) -> bool:
        """Determine whether a page is high-value for future extraction."""
        region_types = {region.region_type for region in vision_result.regions}
        if {"filter_bar", "table", "pagination"}.issubset(region_types):
            return True
        return summary.has_table or vision_result.page_type == "list"

    def _resolved_page_type(self, insight: dict) -> str:
        """Resolve page type with explicit fallback from vision to DOM."""
        page_type_vision = str(insight.get("page_type_vision") or "").strip()
        if page_type_vision and page_type_vision != "unknown":
            return page_type_vision
        page_type_dom = str(insight.get("page_type_dom") or "").strip()
        return page_type_dom or "unknown"

    def _derive_analysis_tags(self, summary: DOMSummary, vision_result: VisionResult) -> list[str]:
        """Derive high-level analysis tags from page understanding."""
        tags: list[str] = []
        if summary.has_table:
            tags.append("data_dense")
        if summary.has_form or vision_result.page_type in {"form", "modal"}:
            tags.append("configuration_surface")
        if any(region.region_type == "tabs" for region in vision_result.regions):
            tags.append("tabbed_workflow")
        if self._is_high_value_page(summary, vision_result):
            tags.append("high_value")
        return tags

    def _build_extraction_summary(self, extraction_rows: list[dict]) -> dict[str, int]:
        """Build summary stats for extraction artifacts."""
        strategy_counts: dict[str, int] = {}
        successful_results = 0

        for row in extraction_rows:
            strategy = str(row.get("strategy", "unknown"))
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
            if row.get("status") == "success":
                successful_results += 1

        return {
            "total_results": len(extraction_rows),
            "successful_results": successful_results,
            "empty_results": sum(1 for row in extraction_rows if row.get("status") == "empty"),
            "failed_results": sum(1 for row in extraction_rows if row.get("status") == "failed"),
            "skipped_results": sum(1 for row in extraction_rows if row.get("status") == "skipped"),
            "strategies": strategy_counts,
        }

    async def _navigate_to_target(self, target: ExplorationTarget) -> bool:
        """Navigate to a route target by URL or click."""
        locator = target.locator
        url_before = await self.controller.get_url()

        if locator.startswith(("http://", "https://", "#", "/")):
            url = locator
            if locator.startswith(("#", "/")):
                parsed = urlparse(url_before)
                if locator.startswith("#"):
                    url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}{locator}"
                else:
                    url = f"{parsed.scheme}://{parsed.netloc}{locator}"
            return await self.controller.goto(url)
        else:
            clicked = await self.controller.click(locator, timeout=self.config.crawl.interaction_timeout)
            if clicked:
                url_after = await self.controller.get_url()
                if url_after == url_before:
                    return False
            return clicked

    async def _capture_and_register(self, target: ExplorationTarget) -> StateSnapshot | None:
        """Capture current page state and register it."""
        try:
            url = await self.controller.get_url()
            title = await self.controller.get_title()
            label = target.label or self._url_to_label(url)

            # Get novelty (for logging, routes are always captured)
            html = await self.controller.get_html()
            novelty, fingerprint = self.novelty_scorer.score(html)
            self.novelty_scorer.register(html, fingerprint)

            screenshot_path = await self.controller.capture_screenshot(label, "route")
            html_path = await self.controller.save_html(label, "route")

            snapshot = StateSnapshot.create(
                target_id=target.id, url=url, title=title,
                screenshot_path=screenshot_path, html_path=html_path,
                visit_status=VisitStatus.SUCCESS, depth=target.depth,
                novelty_score=novelty, dom_fingerprint=fingerprint,
            )

            self.state.register_state(snapshot)
            self.state.mark_visited(target.id)
            self.state.consume_budget()
            self.state.current_state_id = snapshot.id
            self.state.current_target_id = target.id

            console.print(f"[green]  Captured: {url} (novelty={novelty:.2f})[/green]")
            return snapshot

        except Exception as e:
            console.print(f"[red]  Capture failed: {e}[/red]")
            return None

    async def _get_route_url(self, route_target: ExplorationTarget) -> str:
        """Get the full URL for a route target."""
        locator = route_target.locator
        if locator.startswith(("http://", "https://")):
            return locator
        if locator.startswith(("#", "/")):
            base = self.config.target.url
            parsed = urlparse(base)
            if locator.startswith("#"):
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}{locator}"
            return f"{parsed.scheme}://{parsed.netloc}{locator}"
        return locator

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison."""
        parsed = urlparse(url)
        if parsed.fragment and parsed.fragment.startswith("/"):
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}#{parsed.fragment.split('?')[0]}"
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def _url_to_label(self, url: str) -> str:
        """Extract a human-readable label from URL."""
        if "#" in url:
            path = url.split("#")[-1].strip("/")
            return path.replace("/", "_") if path else "root"
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        return path.replace("/", "_") if path else "root"
