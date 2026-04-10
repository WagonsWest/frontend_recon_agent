"""Exploration engine 閳?state machine loop that orchestrates the agent."""

from __future__ import annotations

import asyncio
from collections import Counter
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from rich.console import Console
from rich.panel import Panel

from src.config import AppConfig
from src.agent.engine_executor import ExecutionRuntime
from src.agent.engine_finalizer import FinalizationRuntime
from src.agent.state import (
    AgentPhase, AgentState, ExplorationTarget, StateSnapshot, ActionDecision,
    ActionType, TargetType, VisitStatus, PageCoverage,
)
from src.agent.logger import RunLogger
from src.browser.controller import BrowserController
from src.browser.authenticator import Authenticator
from src.observer.extractor import CandidateExtractor
from src.observer.fingerprint import DOMFingerprinter
from src.observer.novelty import NoveltyScorer
from src.analyzer.page_analyzer import PageAnalyzer
from src.artifacts.manager import ArtifactManager
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
        self.artifacts = ArtifactManager(config)
        self.extraction = ExtractionEngine()
        self.vision = VisionClient(config.vision)
        self.executor = ExecutionRuntime(self)
        self.finalizer = FinalizationRuntime(self)

        # Logger (created lazily after output is cleared)
        self._logger: RunLogger | None = None
        self._log_path = Path(__file__).parent.parent.parent / config.output.artifacts_dir / "run_log.jsonl"

        # Analysis results (state_id -> analysis dict)
        self._analysis_results: dict[str, dict] = {}
        self._vision_results: dict[str, dict] = {}
        self._page_insights: dict[str, dict] = {}
        self._extraction_results: dict[str, dict] = {}
        self._reobservation_count: int = 0
        self._blocked_reason: str = ""
        self._challenge_pause_count: int = 0
        self._observe_breakdown_entries: list[dict[str, object]] = []
        self._site_memory: dict[str, object] = {
            "domain": urlparse(config.target.url).netloc,
            "goal": config.task.goal,
            "goal_keywords": config.task.goal_keywords,
            "page_type_counts": {},
            "selector_success": {},
            "selector_failure": {},
            "label_success": {},
            "label_failure": {},
            "action_type_success": {},
            "action_type_failure": {},
            "challenge_events": [],
            "action_outcomes": [],
        }

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
            f"Goal: {self.config.task.goal}\n"
            f"Profile: {self.config.run.profile}\n"
            f"Budget: {self.config.budget.max_states} states, depth {self.config.budget.max_depth}\n"
            f"Novelty threshold: {self.config.budget.novelty_threshold}",
            title="Agent Configuration",
        ))

        try:
            # INITIALIZE
            await self._phase_initialize()

            # AUTHENTICATE
            await self._phase_authenticate()

            # Prepare the post-auth page before exploration starts.
            current_url = await self._stabilize_post_auth_entry()
            root_target = ExplorationTarget.create(
                target_type=TargetType.ROUTE,
                locator=current_url,
                label=self._url_to_label(current_url),
                depth=0,
                discovery_method="initial_page",
            )
            self.state.add_target(root_target)
            self.state.current_target_id = root_target.id

            # Main agent loop: observe -> decide -> act -> re-observe
            while True:
                if self._blocked_reason:
                    console.print(f"[yellow]Agent paused: {self._blocked_reason}[/yellow]")
                    break

                await self._phase_observe()

                decision = self._phase_decide_next_action()
                if decision is None:
                    break

                snapshot = await self._execute_decision(decision)
                if snapshot is None:
                    continue

                await self._phase_analyze(snapshot)
                if self.config.run.enable_extraction:
                    await self._run_extraction(
                        snapshot,
                        capture_label=decision.label or self._url_to_label(snapshot.url),
                        capture_context="route",
                        allow_vision=True,
                    )

                if self.state.has_budget() and self.config.run.enable_interaction_exploration:
                    target = self.state.targets.get(snapshot.target_id)
                    if target:
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

    # 閳光偓閳光偓 Phase implementations 閳光偓閳光偓

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
                if self.authenticator.manual_abort_requested:
                    ctx["result"] = "aborted"
                    ctx["reason"] = "authentication aborted during manual verification"
                    raise RuntimeError("Authentication aborted during manual verification.")
                ctx["result"] = "retry" if attempt < 2 else "failed"
                ctx["reason"] = f"login attempt {attempt + 1} failed"
            console.print(f"[yellow]Login attempt {attempt + 1} failed, retrying...[/yellow]")
            await asyncio.sleep(3)

        raise RuntimeError("Authentication failed after 3 attempts. Check credentials in config.")

    async def _stabilize_post_auth_entry(self) -> str:
        """Prepare the post-auth page and verify the session before exploration begins."""
        preferred_url = self.config.target.dashboard_url or self.config.target.url
        current_url = await self.controller.get_url()

        for attempt in range(2):
            if preferred_url and self._normalize_url(current_url) != self._normalize_url(preferred_url):
                await self.controller.goto(preferred_url)
                current_url = await self.controller.get_url()

            await self._prepare_page_for_observation(current_url)
            current_url = await self.controller.get_url()
            if not await self.authenticator.check_session():
                self.logger.log(
                    AgentPhase.AUTHENTICATE,
                    "post_auth_session_check",
                    current_url,
                    "retry",
                    "session still looks unauthenticated; re-login",
                )
                if not await self.authenticator.re_login():
                    break
                current_url = await self.controller.get_url()
                continue
            dom_summary = await self._build_dom_summary()
            vision_result = (
                await self._understand_current_page(current_url, dom_summary)
                if self.config.vision.enabled else VisionResult()
            )
            resolved_page_type = (
                vision_result.page_type
                if vision_result.page_type != "unknown"
                else self._infer_dom_page_type(current_url, dom_summary)
            )
            hint_types = Counter(
                str(hint.get("hint_type", "")).strip().lower()
                for hint in vision_result.interaction_hints
                if isinstance(hint, dict) and str(hint.get("hint_type", "")).strip()
            )

            self.logger.log(
                AgentPhase.AUTHENTICATE,
                "stabilize_post_auth",
                current_url,
                "success",
                f"attempt={attempt + 1}, page_type={resolved_page_type}, hint_types={dict(hint_types)}",
            )
            return current_url

        return await self.controller.get_url()

    async def _phase_observe(self) -> None:
        """OBSERVE: Extract route candidates from current page, add to frontier."""
        self.state.phase = AgentPhase.OBSERVE

        current_url = await self.controller.get_url()
        await self._prepare_page_for_observation(current_url)
        current_url = await self.controller.get_url()
        current_target = self.state.targets.get(self.state.current_target_id or "")
        current_depth = current_target.depth if current_target else 0

        if await self._handle_blocking_challenge(current_url, "observe"):
            return
        current_url = await self.controller.get_url()

        # Skip re-observation of already-observed URLs
        normalized_url = self._normalize_url(current_url)
        if normalized_url in self.state.observed_urls:
            return
        self.state.observed_urls.add(normalized_url)

        with self.logger.timed(AgentPhase.OBSERVE, "extract_candidates",
                               current_target.label if current_target else "root") as ctx:
            observe_breakdown: dict[str, int] = {}

            start = time.monotonic()
            candidates, coverage = await self.extractor.extract_all(
                self.controller.page, self.state.current_target_id, current_depth
            )
            observe_breakdown["route_discovery_ms"] = int((time.monotonic() - start) * 1000)

            start = time.monotonic()
            dom_summary = await self._build_dom_summary()
            observe_breakdown["dom_summary_ms"] = int((time.monotonic() - start) * 1000)

            start = time.monotonic()
            vision_result = await self._understand_current_page(current_url, dom_summary)
            observe_breakdown["vision_understanding_ms"] = int((time.monotonic() - start) * 1000)

            start = time.monotonic()
            route_candidates = await self._rerank_route_candidates(
                current_url,
                dom_summary,
                vision_result,
                [c for c in candidates if c.target_type == TargetType.ROUTE],
            )
            observe_breakdown["route_rerank_ms"] = int((time.monotonic() - start) * 1000)

            start = time.monotonic()
            insight = self._build_page_insight(current_url, dom_summary, vision_result)
            self._persist_page_understanding(insight, vision_result)
            observe_breakdown["page_insight_ms"] = int((time.monotonic() - start) * 1000)

            # Only add ROUTE targets to the frontier
            start = time.monotonic()
            added = self.state.add_targets(route_candidates)
            observe_breakdown["frontier_update_ms"] = int((time.monotonic() - start) * 1000)

            start = time.monotonic()
            planned = (
                await self._plan_page_actions(current_url, dom_summary, vision_result)
                if self.config.run.enable_page_action_planning else []
            )
            observe_breakdown["page_action_planning_ms"] = int((time.monotonic() - start) * 1000)
            decisions_added = self.state.add_decisions(planned)
            self._record_observe_breakdown(
                target_label=current_target.label if current_target else "root",
                current_url=current_url,
                route_candidates=route_candidates,
                candidates=candidates,
                breakdown=observe_breakdown,
            )
            ctx["reason"] = (
                f"found {len(route_candidates)} routes, {added} new, "
                f"{decisions_added} actions, page_type={insight.page_type_vision}"
            )

            if current_target and current_target.id not in self.state.coverage:
                self.state.coverage[current_target.id] = coverage

        if added > 0:
            console.print(f"[cyan]  Discovered {added} new routes (frontier: {self.state.frontier_size()})[/cyan]")

    def _record_observe_breakdown(
        self,
        target_label: str,
        current_url: str,
        route_candidates: list[ExplorationTarget],
        candidates: list[ExplorationTarget],
        breakdown: dict[str, int],
    ) -> None:
        total_ms = sum(breakdown.values())
        self._observe_breakdown_entries.append(
            {
                "target": target_label,
                "url": current_url,
                "route_candidates": len(route_candidates),
                "all_candidates": len(candidates),
                "breakdown_ms": breakdown,
                "total_breakdown_ms": total_ms,
            }
        )

    async def _handle_blocking_challenge(self, current_url: str, phase_label: str) -> bool:
        """Detect captcha/anti-bot challenges and pause or resume safely when configured to do so."""
        challenge = await self.controller.detect_captcha_or_antibot()
        if not challenge.get("detected"):
            return False

        reason = (
            f"captcha_or_antibot_detected during {phase_label}: "
            f"selectors={challenge.get('selector_matches', [])}, "
            f"text={challenge.get('text_matches', [])}"
        )
        self.logger.log(AgentPhase.OBSERVE, "blocking_challenge", current_url, "failed", reason)
        if self.config.task.use_site_memory:
            challenge_events = self._site_memory["challenge_events"]
            challenge_events.append({
                "timestamp": datetime.now().isoformat(),
                "url": current_url,
                "phase": phase_label,
                "selector_matches": challenge.get("selector_matches", []),
                "text_matches": challenge.get("text_matches", []),
            })
            if len(challenge_events) > 50:
                del challenge_events[:-50]

        if self.config.task.captcha_policy == "ignore":
            return False

        self.artifacts.save_json(
            "last_challenge.json",
            {
                "timestamp": datetime.now().isoformat(),
                "url": current_url,
                "phase": phase_label,
                "selector_matches": challenge.get("selector_matches", []),
                "text_matches": challenge.get("text_matches", []),
            },
        )

        if self.config.task.human_assistance_allowed:
            resumed = await self._pause_for_human_challenge(current_url, phase_label, challenge)
            if resumed:
                return False

        self._blocked_reason = reason
        return True

    async def _pause_for_human_challenge(
        self,
        current_url: str,
        phase_label: str,
        challenge: dict[str, object],
    ) -> bool:
        """Freeze automation until the user completes a challenge in the visible browser."""
        self._challenge_pause_count += 1
        console.print(
            "[yellow]Challenge detected. Automation is now frozen. "
            "Please complete the verification manually in the visible browser, "
            "then return here and press Enter. Type 'abort' to stop the run.[/yellow]"
        )
        console.print(
            f"[dim]Challenge context: phase={phase_label}, url={current_url}, "
            f"selectors={challenge.get('selector_matches', [])}, "
            f"text={challenge.get('text_matches', [])}[/dim]"
        )

        for attempt in range(5):
            try:
                response = await asyncio.to_thread(
                    console.input,
                    "[bold cyan]Press Enter after the challenge is cleared, or type 'abort' to stop: [/bold cyan]",
                )
            except EOFError:
                self._blocked_reason = "challenge verification aborted because terminal input was unavailable"
                return False

            if response.strip().lower() == "abort":
                self._blocked_reason = "challenge verification aborted by user"
                return False

            await asyncio.sleep(max(self.config.crawl.wait_for_spa / 1000, 1.0))
            follow_up = await self.controller.detect_captcha_or_antibot()
            if not follow_up.get("detected"):
                resumed_url = await self.controller.get_url()
                self.logger.log(
                    AgentPhase.OBSERVE,
                    "challenge_cleared",
                    resumed_url,
                    "success",
                    f"phase={phase_label}, pauses={self._challenge_pause_count}",
                )
                console.print("[green]Challenge cleared. Resuming exploration.[/green]")
                return True

            console.print(
                f"[yellow]Challenge still appears active after attempt {attempt + 1}. "
                "Please finish the verification in the visible browser before continuing.[/yellow]"
            )

        self._blocked_reason = "challenge remained active after repeated human-assistance attempts"
        return False

    async def _prepare_page_for_observation(self, current_url: str) -> None:
        """Leave the page untouched before observation so the model sees the real surface."""
        return

    async def _classify_visible_overlay(self) -> dict[str, object]:
        """Overlay triage is disabled; exploration should stay model-led."""
        return {"action": "keep", "reason": "overlay_triage_disabled"}

    def _phase_decide_next_action(self) -> ActionDecision | None:
        """SELECT_ACTION: Pick the next action in the agent loop."""
        self.state.phase = AgentPhase.SELECT_ACTION

        if not self.state.has_budget():
            self.logger.log(AgentPhase.SELECT_ACTION, "budget_exhausted", "", "success",
                          f"budget exhausted ({self.state.budget_total} states)")
            console.print("[yellow]Budget exhausted[/yellow]")
            return None

        decision = self._select_best_pending_decision()
        frontier_candidate = self._peek_frontier_target()
        if (
            decision is not None
            and frontier_candidate is not None
            and self._should_prefer_route_over_decision(frontier_candidate, decision)
        ):
            self.state.pending_decisions.appendleft(decision)
            decision = None
        if decision is not None:
            self.logger.log(
                AgentPhase.SELECT_ACTION,
                "selected_decision",
                decision.label,
                "success",
                f"type={decision.action_type.value}, reason={decision.reason}",
            )
            return decision

        target = self.state.pop_frontier()
        if target is None and self.state.has_deferred_frontier():
            if self._should_consume_deferred_routes():
                target = self.state.pop_deferred_frontier()
            else:
                self.logger.log(
                    AgentPhase.SELECT_ACTION,
                    "deferred_routes_skipped",
                    "",
                    "success",
                    "only deferred auth/interactive/global-nav routes remained; stopping by policy",
                )
                console.print("[yellow]Primary content frontier exhausted; deferred risk/chrome routes left unvisited by policy[/yellow]")
                return None
        if target is None:
            self.logger.log(AgentPhase.SELECT_ACTION, "frontier_empty", "", "success",
                          "no more routes or decisions to explore")
            console.print("[yellow]Frontier empty 閳?exploration complete[/yellow]")
            return None

        self.logger.log(AgentPhase.SELECT_ACTION, "selected_target", target.label, "success",
                      f"type={target.target_type.value}, depth={target.depth}")
        return ActionDecision(
            action_type=ActionType.NAVIGATE,
            target_id=target.id,
            label=target.label,
            reason="selected next route from observed candidates",
            metadata={"target_type": target.target_type.value, "depth": target.depth},
        )

    def _should_consume_deferred_routes(self) -> bool:
        """Deferred-route policy is disabled; candidate ordering is model-led."""
        return True

    def _peek_frontier_target(self) -> ExplorationTarget | None:
        for target_id in self.state.frontier:
            if target_id in self.state.visited or target_id in self.state.skipped:
                continue
            target = self.state.targets.get(target_id)
            if target is not None:
                return target
        return None

    def _should_prefer_route_over_decision(self, target: ExplorationTarget, decision: ActionDecision) -> bool:
        if target.target_type != TargetType.ROUTE:
            return False
        if decision.action_type == ActionType.FILL_AND_SUBMIT_FORM:
            return False

        current_state = self.state.states.get(self.state.current_state_id or "")
        current_url = self._normalize_url(current_state.url) if current_state else ""
        same_url_states = sum(
            1 for snapshot in self.state.states.values()
            if self._normalize_url(snapshot.url) == current_url
        )
        if same_url_states < 2:
            return False

        route_score = self._score_route_target(target)
        decision_score = self._score_decision(decision)
        return len(self.state.pending_decisions) >= 4 and route_score >= decision_score + 2

    async def _execute_decision(self, decision: ActionDecision) -> StateSnapshot | None:
        """Execute a planned decision from the agent loop."""
        return await self.executor.execute_decision(decision)

    async def _execute_page_action_decision(self, decision: ActionDecision) -> StateSnapshot | None:
        """Execute a page-level decision such as clicking a CTA, opening a modal, or switching a tab."""
        return await self.executor.execute_page_action_decision(decision)

    async def _execute_form_decision(self, decision: ActionDecision) -> StateSnapshot | None:
        """Fill a visible form heuristically and submit it."""
        return await self.executor.execute_form_decision(decision)

    async def _execute_route(self, target: ExplorationTarget) -> StateSnapshot | None:
        """Navigate to a route and capture it. Routes are always captured."""
        return await self.executor.execute_route(target)
        step = self.state.next_step()
        console.print(f"\n[bold cyan]Step {step}: route 閳?{target.label}[/bold cyan]")

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
            self._remember_action_outcome(
                ActionDecision(
                    action_type=ActionType.NAVIGATE,
                    target_id=target.id,
                    label=target.label,
                    metadata={"selector": target.locator, "context": "route"},
                ),
                False,
                "navigation_failed",
            )
            return None

        # Check session
        if not await self.authenticator.check_session():
            await self.authenticator.re_login()
            return None

        # Routes are ALWAYS captured
        snapshot = await self._capture_and_register(target)
        if snapshot:
            self._remember_action_outcome(
                ActionDecision(
                    action_type=ActionType.NAVIGATE,
                    target_id=target.id,
                    label=target.label,
                    metadata={"selector": target.locator, "context": "route"},
                ),
                True,
                "captured_route",
            )
        if snapshot and self.config.task.reobserve_on_state_change:
            await self._reobserve_current_state(
                state_id=snapshot.id,
                current_url=snapshot.url,
                reason="route_capture",
                allow_vision=True,
                discover_candidates=False,
            )
        return snapshot

    async def _explore_page_interactions(self, route_target: ExplorationTarget) -> None:
        await self.executor.explore_page_interactions(route_target)
        return
        """Explore all interactions on the current page inline (no frontier).

        Order: action dropdowns 閳?dropdown items 閳?add buttons 閳?tabs 閳?expand rows.
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

        # 閳光偓閳光偓 1. Action dropdown 閳?click each item 閳光偓閳光偓
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
                            # Might have navigated to a new page 閳?go back
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

        # 閳光偓閳光偓 2. Add/create button 閳?modal 閳光偓閳光偓
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

        # 閳光偓閳光偓 3. Expandable rows 閳光偓閳光偓
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

        # 閳光偓閳光偓 4. Tabs 閳光偓閳光偓
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
        return await self.executor.capture_interaction(label, parent_target, context)
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
            console.print(f"[dim]    Low novelty ({novelty:.2f}) 閳?skipped[/dim]")
            self.logger.log(AgentPhase.EVAL_NOVELTY, "skip_interaction", label,
                          "skipped", f"novelty={novelty:.2f}")
            return "skipped_novelty"

        # Capture
        url = await self.controller.get_url()
        title = await self.controller.get_title()
        screenshot_path = await self.controller.capture_screenshot(label, context)
        report_screenshot_path = ""
        if self.config.run.capture_report_screenshots:
            report_screenshot_path = await self._capture_report_screenshot(
                label,
                context,
                prefer_full_page=False,
            )
        html_path = await self.controller.save_html(label, context)

        snapshot = StateSnapshot.create(
            target_id=parent_target.id,
            url=url, title=title,
            screenshot_path=screenshot_path, html_path=html_path,
            visit_status=VisitStatus.SUCCESS,
            depth=parent_target.depth + 1,
            novelty_score=novelty, dom_fingerprint=fingerprint,
            metadata={
                "capture_label": label,
                "capture_context": context,
                "report_screenshot_path": report_screenshot_path,
            },
        )
        self.state.register_state(snapshot)
        self.state.consume_budget()
        self.novelty_scorer.register(html, fingerprint)

        self.state.current_state_id = snapshot.id

        # Analyze
        computed_styles = await self.controller.get_computed_styles()
        analysis = self.analyzer.analyze(html, computed_styles)
        self._analysis_results[snapshot.id] = analysis
        self.artifacts.save_analysis(snapshot.id, analysis)
        if self.config.task.reobserve_on_state_change:
            await self._reobserve_current_state(
                state_id=snapshot.id,
                current_url=url,
                reason=context,
                allow_vision=self.config.task.use_vision_on_state_change,
                discover_candidates=False,
            )
        if self.config.run.enable_extraction:
            await self._run_extraction(
                snapshot,
                capture_label=label,
                capture_context=context,
                allow_vision=self.config.task.use_vision_on_state_change,
            )

        self.logger.log(AgentPhase.EXECUTE, f"capture_{context}", label,
                      "success", f"novelty={novelty:.2f}")
        console.print(f"[green]    Captured: {url} (novelty={novelty:.2f})[/green]")
        return "captured"

    async def _capture_report_screenshot(
        self,
        label: str,
        context: str,
        prefer_full_page: bool,
    ) -> str:
        return await self.executor.capture_report_screenshot(label, context, prefer_full_page)
        """Capture the image variant best suited for the human-readable report."""
        if prefer_full_page:
            return await self.controller.capture_screenshot(label, f"{context}_report")
        return await self.controller.capture_viewport_screenshot(label, f"{context}_report")

    async def _phase_analyze(self, snapshot: StateSnapshot) -> None:
        await self.executor.phase_analyze(snapshot)
        return
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
        await self.executor.run_extraction(snapshot, capture_label, capture_context, allow_vision)
        return
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
            page_insight=insight,
            vision_result=self._vision_results.get(snapshot.id),
        )
        result.capture_label = capture_label
        result.capture_context = capture_context
        self._extraction_results[snapshot.id] = result.model_dump()

    async def _phase_finalize(self) -> None:
        await self.finalizer.phase_finalize()
        return
    def _observe_breakdown_summary(self) -> dict[str, object]:
        return self.finalizer.observe_breakdown_summary()
        entries = list(self._observe_breakdown_entries)
        aggregate: dict[str, dict[str, float]] = {}
        for entry in entries:
            breakdown = entry.get("breakdown_ms", {})
            if not isinstance(breakdown, dict):
                continue
            for key, value in breakdown.items():
                bucket = aggregate.setdefault(key, {"count": 0, "total_ms": 0})
                bucket["count"] += 1
                bucket["total_ms"] += int(value)

        for bucket in aggregate.values():
            count = int(bucket["count"]) or 1
            bucket["avg_ms"] = round(bucket["total_ms"] / count, 2)

        slowest = sorted(
            entries,
            key=lambda entry: int(entry.get("total_breakdown_ms", 0)),
            reverse=True,
        )[:10]

        return {
            "count": len(entries),
            "aggregate_ms": aggregate,
            "slowest_observe_calls": slowest,
            "entries": entries,
        }

    # 閳光偓閳光偓 Helpers 閳光偓閳光偓

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

    async def _plan_page_actions(
        self,
        current_url: str,
        dom_summary: DOMSummary | None = None,
        vision_result: VisionResult | None = None,
    ) -> list[ActionDecision]:
        """Plan page-level next actions from the current visible state."""
        decisions: list[ActionDecision] = []
        url_key = self._normalize_url(current_url)
        resolved_dom_summary = dom_summary or await self._build_dom_summary()
        resolved_vision = vision_result or VisionResult()
        resolved_page_type = resolved_vision.page_type
        if resolved_page_type == "unknown":
            resolved_page_type = self._infer_dom_page_type(current_url, resolved_dom_summary)
        auth_surface = resolved_page_type == "auth"

        # Non-active tabs
        try:
            tabs = self.controller.page.locator(self.config.interaction.tab_selector)
            tab_count = await tabs.count()
            for i in range(min(tab_count, 4)):
                tab = tabs.nth(i)
                if not await tab.is_visible():
                    continue
                label = (await tab.text_content() or "").strip() or f"tab_{i + 1}"
                decisions.append(ActionDecision(
                    action_type=ActionType.SWITCH_TAB,
                    target_id=self.state.current_target_id,
                    label=label,
                    reason="visible non-active tab discovered",
                    dedup_key=f"tab:{url_key}:{label}:{i}",
                    metadata={
                        "selector": self.config.interaction.tab_selector,
                        "index": i,
                        "context": "tab_state",
                    },
                ))
        except Exception:
            pass

        # Add / create buttons
        try:
            for selector in self.config.interaction.add_button_selectors:
                added_for_selector = False
                locator = self.controller.page.locator(selector)
                count = await locator.count()
                for i in range(min(count, 2)):
                    button = locator.nth(i)
                    if not await button.is_visible():
                        continue
                    label = (await button.text_content() or "").strip() or f"add_{i + 1}"
                    decisions.append(ActionDecision(
                        action_type=ActionType.OPEN_MODAL,
                        target_id=self.state.current_target_id,
                        label=label,
                        reason="visible add/create button discovered",
                        dedup_key=f"modal:{url_key}:{label}:{selector}:{i}",
                        metadata={
                            "selector": selector,
                            "index": i,
                            "context": "modal",
                        },
                    ))
                    added_for_selector = True
                if added_for_selector:
                    break
        except Exception:
            pass

        if not auth_surface:
            try:
                click_candidates = await self._collect_click_action_candidates(current_url)
                decisions.extend(
                    await self._rank_page_action_candidates(
                        current_url,
                        resolved_dom_summary,
                        resolved_vision,
                        click_candidates,
                    )
                )
            except Exception:
                pass

        # Auth / onboarding forms should only run on explicit auth surfaces.
        if auth_surface and (self.config.task.allow_login_flows or self.config.task.allow_registration_flows):
            try:
                form_decision = await self._plan_form_action(current_url)
                if form_decision:
                    decisions.append(form_decision)
            except Exception:
                pass

        return decisions

    async def _plan_workspace_actions(self, current_url: str) -> list[ActionDecision]:
        """Legacy helper kept only for compatibility while model-led planning takes over."""
        return []

    async def _collect_click_action_candidates(self, current_url: str) -> list[ActionDecision]:
        """Collect broad visible click candidates and defer prioritization to the model."""
        selector = "button, a, [role='button'], [role='tab'], [aria-haspopup='menu']"
        specs = await self.controller.evaluate(
            """
            (selector) => {
              const isVisible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                if (!rect.width || !rect.height) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                if (el.closest('[hidden], [aria-hidden="true"]')) return false;
                return true;
              };

              return Array.from(document.querySelectorAll(selector)).map((el, index) => {
                if (!isVisible(el)) return null;
                const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                const ariaLabel = (el.getAttribute('aria-label') || '').trim();
                const title = (el.getAttribute('title') || '').trim();
                const href = (el.getAttribute('href') || '').trim();
                const role = (el.getAttribute('role') || '').trim().toLowerCase();
                let region = 'other';
                if (el.closest('aside, nav, [role="navigation"]')) {
                  region = 'nav';
                } else if (el.closest('main, [role="main"]')) {
                  region = 'main';
                } else if (el.closest('[role="dialog"], [aria-modal="true"]')) {
                  region = 'modal';
                }
                return {
                  index,
                  text,
                  ariaLabel,
                  title,
                  href,
                  role,
                  region,
                  tag: el.tagName.toLowerCase(),
                  hasPopup: (el.getAttribute('aria-haspopup') || '').trim(),
                };
              }).filter(Boolean);
            }
            """,
            selector,
            default=[],
        )

        if not specs:
            return []

        url_key = self._normalize_url(current_url)
        destructive = tuple(keyword.lower() for keyword in self.config.exploration.destructive_keywords)
        decisions: list[ActionDecision] = []
        seen: set[str] = set()

        for spec in specs[:30]:
            label = " ".join(
                str(spec.get(key, "") or "") for key in ("text", "ariaLabel", "title")
            ).strip()
            label = " ".join(label.split())
            if not label or len(label) > 80:
                continue

            lowered = label.lower()
            href = str(spec.get("href", "") or "").strip()
            href_lower = href.lower()
            if any(keyword and keyword in lowered for keyword in destructive):
                continue
            if href_lower.startswith(("mailto:", "javascript:")) or href_lower.endswith((".pdf", ".zip")):
                continue

            role = str(spec.get("role", "") or "").lower()
            region = str(spec.get("region", "") or "other").lower()
            action_type = ActionType.SWITCH_TAB if role == "tab" else ActionType.CLICK_ACTION
            context = "tab_state" if role == "tab" else (region or "page_action")
            dedup_key = f"click:{url_key}:{label}:{href_lower}:{role}:{context}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            decisions.append(
                ActionDecision(
                    action_type=action_type,
                    target_id=self.state.current_target_id,
                    label=label,
                    reason="visible interactive element discovered",
                    dedup_key=dedup_key,
                    metadata={
                        "selector": selector,
                        "index": int(spec.get("index", 0)),
                        "context": context,
                        "region": region,
                        "role": role,
                        "tag": str(spec.get("tag", "") or ""),
                        "href": href,
                        "has_popup": bool(spec.get("hasPopup")),
                    },
                )
            )

        return decisions

    async def _rank_page_action_candidates(
        self,
        current_url: str,
        dom_summary: DOMSummary,
        vision_result: VisionResult,
        decisions: list[ActionDecision],
    ) -> list[ActionDecision]:
        """Use the model to rank visible page-action candidates."""
        if not decisions:
            return []

        page_type = vision_result.page_type
        if page_type == "unknown":
            page_type = self._infer_dom_page_type(current_url, dom_summary)

        candidates = [
            {
                "index": index,
                "label": decision.label,
                "action_type": decision.action_type.value,
                "context": str(decision.metadata.get("context", "")),
                "region": str(decision.metadata.get("region", "")),
                "role": str(decision.metadata.get("role", "")),
                "tag": str(decision.metadata.get("tag", "")),
                "href": str(decision.metadata.get("href", "")),
            }
            for index, decision in enumerate(decisions)
        ]
        ranking = await self.vision.rank_candidates(
            kind="page_action",
            goal=self.config.task.goal,
            url=current_url,
            page_type=page_type,
            dom_summary=dom_summary,
            interaction_hints=vision_result.interaction_hints,
            candidates=candidates,
        )
        return self._apply_model_ranking_to_decisions(decisions, ranking.notes, ranking.choices)

    async def _plan_form_action(self, current_url: str) -> ActionDecision | None:
        """Plan a generic form-fill action for login/signup/onboarding flows."""
        inputs = self.controller.page.locator("input, textarea")
        input_count = await inputs.count()
        visible_count = 0
        for i in range(min(input_count, 8)):
            try:
                if await inputs.nth(i).is_visible():
                    visible_count += 1
            except Exception:
                continue
        if visible_count == 0:
            return None

        buttons = self.controller.page.locator("button, [role='button'], input[type='submit']")
        button_count = await buttons.count()
        keywords = (
            "sign up", "register", "create account", "continue", "next",
            "submit", "finish", "complete", "login", "sign in", "join"
        )
        for i in range(min(button_count, 12)):
            try:
                button = buttons.nth(i)
                if not await button.is_visible():
                    continue
                text = " ".join(((await button.text_content()) or "").split()).strip()
                value_attr = (await button.get_attribute("value") or "").strip()
                label = text or value_attr
                if not label:
                    continue
                lower = label.lower()
                if not any(keyword in lower for keyword in keywords):
                    continue
                return ActionDecision(
                    action_type=ActionType.FILL_AND_SUBMIT_FORM,
                    target_id=self.state.current_target_id,
                    label=label,
                    reason="visible auth/onboarding form with submit-like CTA",
                    dedup_key=f"form:{self._normalize_url(current_url)}:{label}:{i}",
                    metadata={
                        "submit_selector": "button, [role='button'], input[type='submit']",
                        "submit_index": i,
                    },
                )
            except Exception:
                continue
        return None

    async def _fill_visible_form_fields(self) -> int:
        """Fill visible form fields with heuristic values from task/login config."""
        inputs = self.controller.page.locator("input, textarea")
        count = await inputs.count()
        filled = 0

        for i in range(min(count, 20)):
            try:
                field = inputs.nth(i)
                if not await field.is_visible():
                    continue
                input_type = ((await field.get_attribute("type")) or "text").lower()
                if input_type in {"hidden", "submit", "checkbox", "radio", "file"}:
                    continue
                current_value = (await field.input_value() or "").strip()
                if current_value:
                    continue

                name_hint = " ".join(filter(None, [
                    await field.get_attribute("name"),
                    await field.get_attribute("id"),
                    await field.get_attribute("placeholder"),
                    await field.get_attribute("aria-label"),
                    await field.get_attribute("autocomplete"),
                ])).lower()

                value = self._guess_form_value(name_hint, input_type)
                if value is None:
                    continue

                await field.fill(value)
                filled += 1
            except Exception:
                continue

        return filled

    def _guess_form_value(self, name_hint: str, input_type: str) -> str | None:
        """Map a field hint to a reasonable task/login value."""
        login_username = self.config.login.username or self.config.task.profile_email
        login_password = self.config.login.password or self.config.task.profile_password

        if input_type == "email" or any(key in name_hint for key in ["email", "e-mail"]):
            return self.config.task.profile_email or login_username
        if input_type == "password" or "password" in name_hint:
            return login_password
        if any(key in name_hint for key in ["user", "login", "account"]):
            return login_username
        if any(key in name_hint for key in ["name", "full name", "fullname"]):
            return self.config.task.profile_name
        if any(key in name_hint for key in ["company", "organization", "org", "business"]):
            return self.config.task.profile_company
        if any(key in name_hint for key in ["phone", "mobile", "tel"]):
            return "13800138000"
        if any(key in name_hint for key in ["code", "otp", "verification"]):
            return None
        if input_type in {"text", "search"}:
            return self.config.task.profile_name
        return None

    async def _reobserve_current_state(
        self,
        state_id: str,
        current_url: str,
        reason: str,
        allow_vision: bool,
        discover_candidates: bool,
    ) -> None:
        """Refresh page understanding after a meaningful state change."""
        if self._reobservation_count >= self.config.task.max_reobservations_per_run:
            return
        await self._prepare_page_for_observation(current_url)
        current_url = await self.controller.get_url()
        if await self._handle_blocking_challenge(current_url, f"reobserve:{reason}"):
            return
        current_url = await self.controller.get_url()

        self._reobservation_count += 1
        dom_summary = await self._build_dom_summary()
        vision_result = (
            await self._understand_current_page(current_url, dom_summary)
            if allow_vision else VisionResult()
        )
        insight = self._build_page_insight(
            current_url,
            dom_summary,
            vision_result,
            state_id=state_id,
        )
        self._persist_page_understanding(insight, vision_result)

        if discover_candidates:
            current_target = self.state.targets.get(self.state.current_target_id or "")
            current_depth = current_target.depth if current_target else 0
            candidates, _ = await self.extractor.extract_all(
                self.controller.page, self.state.current_target_id, current_depth
            )
            route_candidates = await self._rerank_route_candidates(
                current_url,
                dom_summary,
                vision_result,
                [c for c in candidates if c.target_type == TargetType.ROUTE],
            )
            self.state.add_targets(route_candidates)

        planned = (
            await self._plan_page_actions(current_url, dom_summary, vision_result)
            if self.config.run.enable_page_action_planning else []
        )
        self.state.add_decisions(planned)

        self.logger.log(
            AgentPhase.OBSERVE,
            "reobserve_state",
            current_url,
            "success",
            f"reason={reason}, page_type={insight.page_type_vision or insight.page_type_dom}",
        )

    async def _rerank_route_candidates(
        self,
        current_url: str,
        dom_summary: DOMSummary,
        vision_result: VisionResult,
        route_candidates: list[ExplorationTarget],
    ) -> list[ExplorationTarget]:
        """Rerank route candidates with model-led next-step selection."""
        if not route_candidates:
            return route_candidates

        page_type = vision_result.page_type
        if page_type == "unknown":
            page_type = self._infer_dom_page_type(current_url, dom_summary)

        candidates = [
            {
                "index": index,
                "label": candidate.label,
                "locator": candidate.locator,
                "depth": candidate.depth,
                "region": str(candidate.metadata.get("region", "")),
                "context": str(candidate.metadata.get("context", "")),
                "discovery_method": candidate.discovery_method,
            }
            for index, candidate in enumerate(route_candidates)
        ]
        ranking = await self.vision.rank_candidates(
            kind="route",
            goal=self.config.task.goal,
            url=current_url,
            page_type=page_type,
            dom_summary=dom_summary,
            interaction_hints=vision_result.interaction_hints,
            candidates=candidates,
        )
        return self._apply_model_ranking_to_routes(route_candidates, ranking.notes, ranking.choices)

    def _build_page_insight(self, current_url: str, dom_summary: DOMSummary,
                            vision_result: VisionResult, state_id: str | None = None) -> PageInsight:
        """Build a merged page insight from DOM and vision understanding."""
        insight_state_id = state_id or self.state.current_state_id or f"observe_{self._url_to_label(current_url)}"
        page_type_dom = self._infer_dom_page_type(current_url, dom_summary)

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
        self._remember_page_type(self._resolved_page_type(insight.model_dump()))

        if self.config.vision.enabled:
            self._vision_results[insight.state_id] = vision_result.model_dump()
            self.artifacts.save_vision(insight.state_id, vision_result.model_dump())

    def _current_page_insight(self) -> dict[str, object] | None:
        current_state = self.state.states.get(self.state.current_state_id or "")
        if current_state:
            insight = self._page_insights.get(current_state.id)
            if insight:
                return insight
            return self._latest_page_insight_for_url(current_state.url)

        current_target = self.state.targets.get(self.state.current_target_id or "")
        if current_target and current_target.locator.startswith(("http://", "https://")):
            return self._latest_page_insight_for_url(current_target.locator)
        return None

    def _latest_page_insight_for_url(self, url: str) -> dict[str, object] | None:
        normalized = self._normalize_url(url)
        for insight in reversed(list(self._page_insights.values())):
            insight_url = self._normalize_url(str(insight.get("url", "")))
            if insight_url == normalized:
                return insight
        return None

    def _apply_model_ranking_to_routes(
        self,
        route_candidates: list[ExplorationTarget],
        notes: str,
        choices: list[object],
    ) -> list[ExplorationTarget]:
        """Attach model scores to route candidates and return them sorted."""
        ranked_indexes: set[int] = set()
        total = len(route_candidates)

        for rank, choice in enumerate(choices):
            index = int(getattr(choice, "index", -1))
            if index < 0 or index >= total or index in ranked_indexes:
                continue
            ranked_indexes.add(index)
            candidate = route_candidates[index]
            candidate.metadata["model_signal"] = max(total - rank, 1)
            candidate.metadata["model_rank"] = rank + 1
            candidate.metadata["model_reason"] = str(getattr(choice, "reason", "") or "")
            if notes:
                candidate.metadata["model_notes"] = notes

        for index, candidate in enumerate(route_candidates):
            if index in ranked_indexes:
                continue
            candidate.metadata.setdefault("model_signal", 0)
            if notes:
                candidate.metadata.setdefault("model_notes", notes)

        return sorted(route_candidates, key=lambda item: (-self._score_route_target(item), item.depth, item.label.lower()))

    def _apply_model_ranking_to_decisions(
        self,
        decisions: list[ActionDecision],
        notes: str,
        choices: list[object],
    ) -> list[ActionDecision]:
        """Attach model scores to page-action candidates and return the top items."""
        ranked_indexes: set[int] = set()
        total = len(decisions)

        for rank, choice in enumerate(choices):
            index = int(getattr(choice, "index", -1))
            if index < 0 or index >= total or index in ranked_indexes:
                continue
            ranked_indexes.add(index)
            decision = decisions[index]
            decision.metadata["model_signal"] = max(total - rank, 1)
            decision.metadata["model_rank"] = rank + 1
            decision.metadata["model_reason"] = str(getattr(choice, "reason", "") or "")
            if notes:
                decision.metadata["model_notes"] = notes

        for index, decision in enumerate(decisions):
            if index in ranked_indexes:
                continue
            decision.metadata.setdefault("model_signal", 0)
            if notes:
                decision.metadata.setdefault("model_notes", notes)

        ordered = sorted(decisions, key=lambda item: (-self._score_decision(item), item.label.lower()))
        return ordered[:6]

    def _score_route_target(
        self,
        candidate: ExplorationTarget,
        *,
        page_type: str | None = None,
        interaction_hints: list[dict] | list | None = None,
    ) -> int:
        return int(candidate.metadata.get("model_signal", 0))

    def _select_best_pending_decision(self) -> ActionDecision | None:
        """Select the strongest pending decision using goal and memory signals."""
        if not self.state.pending_decisions:
            return None

        indexed = list(enumerate(self.state.pending_decisions))
        best_index, best_decision = max(
            indexed,
            key=lambda item: (self._score_decision(item[1]), -item[0]),
        )
        remaining = [
            decision for idx, decision in indexed
            if idx != best_index
        ]
        from collections import deque
        self.state.pending_decisions = deque(remaining)
        return best_decision

    def _score_decision(self, decision: ActionDecision) -> int:
        """Score a decision using only model-provided ranking signals."""
        return int(decision.metadata.get("model_signal", 0))

    async def _capture_runtime_signature(self) -> dict[str, str | bool]:
        """Capture a lightweight runtime signature for action validation."""
        url = await self.controller.get_url()
        title = await self.controller.get_title()
        html = await self.controller.get_html()
        _, fingerprint = self.novelty_scorer.score(html)
        modal_open = await self.controller.is_modal_open()
        return {
            "url": self._normalize_url(url),
            "title": title,
            "fingerprint": fingerprint,
            "modal_open": modal_open,
        }

    def _state_changed_meaningfully(
        self,
        before: dict[str, str | bool],
        after: dict[str, str | bool],
    ) -> bool:
        """Check whether an action changed the page state in a meaningful way."""
        for key in ("url", "title", "fingerprint", "modal_open"):
            if before.get(key) != after.get(key):
                return True
        return False

    def _remember_page_type(self, page_type: str) -> None:
        """Track page-type observations for this site."""
        if not self.config.task.use_site_memory or not page_type:
            return
        counts = self._site_memory["page_type_counts"]
        counts[page_type] = int(counts.get(page_type, 0)) + 1

    def _remember_action_outcome(self, decision: ActionDecision, success: bool, reason: str) -> None:
        """Track lightweight site memory about what tends to work on this domain."""
        if not self.config.task.use_site_memory:
            return

        selector = str(decision.metadata.get("selector", "")).strip()
        label = decision.label.lower().strip()
        action_type = decision.action_type.value
        outcome_key = "success" if success else "failure"

        selector_bucket = self._site_memory[f"selector_{outcome_key}"]
        if selector:
            selector_bucket[selector] = int(selector_bucket.get(selector, 0)) + 1

        label_bucket = self._site_memory[f"label_{outcome_key}"]
        if label:
            label_bucket[label] = int(label_bucket.get(label, 0)) + 1

        action_bucket = self._site_memory[f"action_type_{outcome_key}"]
        action_bucket[action_type] = int(action_bucket.get(action_type, 0)) + 1

        outcomes = self._site_memory["action_outcomes"]
        outcomes.append({
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type,
            "label": decision.label,
            "selector": selector,
            "context": decision.metadata.get("context", ""),
            "success": success,
            "reason": reason,
        })
        if len(outcomes) > 100:
            del outcomes[:-100]

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

    def _infer_dom_page_type(self, current_url: str, summary: DOMSummary) -> str:
        """Infer a coarse page type from structural DOM signals only."""
        components = set(summary.component_types)

        if summary.has_modal:
            return "modal"
        if "table" in components and (summary.table_headers or summary.has_pagination):
            return "list"
        if "form" in components:
            return "form"
        if summary.has_pagination:
            return "list"
        if "tabs" in components and "table" not in components:
            return "detail"
        if "card" in components and "table" not in components and "form" not in components and summary.nav_labels:
            return "dashboard"
        if summary.nav_labels or summary.button_labels or summary.title:
            return "content"
        return "unknown"

    def _choose_extraction_strategy(self, page_type_dom: str, page_type_vision: str) -> str:
        """Choose the provisional extraction strategy for a page."""
        page_type = page_type_vision if page_type_vision != "unknown" else page_type_dom
        if page_type == "list":
            return "list_table"
        if page_type == "detail":
            return "detail_fields"
        if page_type in {"form", "modal", "auth"}:
            return "form_schema"
        if page_type in {"landing", "content", "docs"}:
            return "content_blocks"
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
        if summary.has_form or vision_result.page_type in {"form", "modal", "auth"}:
            tags.append("interactive_surface")
        if vision_result.page_type in {"landing", "content", "docs"}:
            tags.append("content_surface")
        if vision_result.page_type == "docs":
            tags.append("documentation_surface")
        if any(region.region_type == "tabs" for region in vision_result.regions):
            tags.append("tabbed_workflow")
        if self._is_high_value_page(summary, vision_result):
            tags.append("high_value")
        return tags

    def _build_extraction_summary(self, extraction_rows: list[dict]) -> dict[str, int]:
        """Build summary stats for extraction artifacts."""
        return self.finalizer.build_extraction_summary(extraction_rows)
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
        return await self.executor.navigate_to_target(target)
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
        return await self.executor.capture_and_register(target)
        try:
            url = await self.controller.get_url()
            title = await self.controller.get_title()
            label = target.label or self._url_to_label(url)

            # Get novelty (for logging, routes are always captured)
            html = await self.controller.get_html()
            novelty, fingerprint = self.novelty_scorer.score(html)
            self.novelty_scorer.register(html, fingerprint)

            screenshot_path = await self.controller.capture_screenshot(
                label,
                "route",
                full_page=(target.depth == 0),
            )
            report_screenshot_path = ""
            if self.config.run.capture_report_screenshots:
                report_screenshot_path = await self._capture_report_screenshot(
                    label,
                    "route",
                    prefer_full_page=(target.depth == 0),
                )
            html_path = await self.controller.save_html(label, "route")

            snapshot = StateSnapshot.create(
                target_id=target.id, url=url, title=title,
                screenshot_path=screenshot_path, html_path=html_path,
                visit_status=VisitStatus.SUCCESS, depth=target.depth,
                novelty_score=novelty, dom_fingerprint=fingerprint,
                metadata={
                    "capture_label": label,
                    "capture_context": "route",
                    "report_screenshot_path": report_screenshot_path,
                },
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
        return await self.executor.get_route_url(route_target)
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
