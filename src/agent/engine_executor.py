"""Execution and capture runtime extracted from the main engine."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from rich.console import Console

from src.agent.state import (
    ActionDecision,
    ActionType,
    AgentPhase,
    ExplorationTarget,
    PageCoverage,
    StateSnapshot,
    VisitStatus,
)
from src.extraction.types import EvidencePaths
from src.vision.types import VisionResult

if TYPE_CHECKING:
    from src.agent.engine import ExplorationEngine

console = Console()


class ExecutionRuntime:
    """Owns execution, capture, analyze, and extraction helpers."""

    def __init__(self, engine: "ExplorationEngine"):
        self.engine = engine

    async def execute_decision(self, decision: ActionDecision) -> StateSnapshot | None:
        if decision.action_type == ActionType.NAVIGATE:
            target = self.engine.state.targets.get(decision.target_id or "")
            if not target:
                return None
            snapshot = await self.execute_route(target)
            if snapshot:
                self.engine.state.mark_decision_executed(decision)
            return snapshot

        if decision.action_type in {ActionType.SWITCH_TAB, ActionType.OPEN_MODAL, ActionType.CLICK_ACTION}:
            snapshot = await self.execute_page_action_decision(decision)
            if snapshot:
                self.engine.state.mark_decision_executed(decision)
            return snapshot

        if decision.action_type == ActionType.FILL_AND_SUBMIT_FORM:
            snapshot = await self.execute_form_decision(decision)
            if snapshot:
                self.engine.state.mark_decision_executed(decision)
            return snapshot

        self.engine.logger.log(
            AgentPhase.EXECUTE,
            "unsupported_decision",
            decision.label,
            "skipped",
            f"action_type={decision.action_type.value}",
        )
        return None

    async def execute_page_action_decision(self, decision: ActionDecision) -> StateSnapshot | None:
        current_target = self.engine.state.targets.get(self.engine.state.current_target_id or "")
        if not current_target:
            self.engine.logger.log(
                AgentPhase.EXECUTE,
                "page_action_skipped",
                decision.label,
                "failed",
                "no current target",
            )
            return None

        selector = str(decision.metadata.get("selector", "")).strip()
        index = int(decision.metadata.get("index", 0))
        context = str(decision.metadata.get("context", "step_transition"))
        wait_seconds = float(self.engine.config.crawl.wait_after_navigation) / 1000

        try:
            before = await self.engine._capture_runtime_signature()
            locator = await self._resolve_decision_locator(selector, index, decision.label)
            if locator is None:
                self.engine.logger.log(
                    AgentPhase.EXECUTE,
                    "page_action_skipped",
                    decision.label,
                    "failed",
                    "decision locator not found",
                )
                self.engine._remember_action_outcome(decision, False, "selector_index_out_of_range")
                return None
            if not await locator.is_visible():
                self.engine.logger.log(
                    AgentPhase.EXECUTE,
                    "page_action_skipped",
                    decision.label,
                    "failed",
                    "target not visible",
                )
                self.engine._remember_action_outcome(decision, False, "target_not_visible")
                return None
            if not await self.engine.controller.click_locator(locator, wait=wait_seconds):
                self.engine.logger.log(
                    AgentPhase.EXECUTE,
                    "page_action_skipped",
                    decision.label,
                    "failed",
                    "click failed",
                )
                self.engine._remember_action_outcome(decision, False, "click_failed")
                return None
            after = await self.engine._capture_runtime_signature()
            if self.engine.config.task.validate_action_outcomes and not self.engine._state_changed_meaningfully(before, after):
                self.engine.logger.log(
                    AgentPhase.EXECUTE,
                    "page_action_no_effect",
                    decision.label,
                    "failed",
                    "no meaningful state change detected",
                )
                self.engine._remember_action_outcome(decision, False, "no_state_change")
                return None

            result = await self.capture_interaction(decision.label, current_target, context)
            if result == "captured":
                self.engine._remember_action_outcome(decision, True, "captured")
            elif result == "skipped_novelty":
                self.engine._remember_action_outcome(decision, True, "state_changed_low_novelty")
            else:
                self.engine._remember_action_outcome(decision, False, result)
            if result != "captured":
                return None
            current_state_id = self.engine.state.current_state_id or ""
            return self.engine.state.states.get(current_state_id)
        except Exception as e:
            self.engine.logger.log(
                AgentPhase.EXECUTE,
                "page_action_failed",
                decision.label,
                "failed",
                str(e),
            )
            self.engine._remember_action_outcome(decision, False, str(e))
            return None

    async def _resolve_decision_locator(self, selector: str, index: int, label: str):
        locator = self.engine.controller.page.locator(selector)
        count = await locator.count()
        if count > index:
            candidate = locator.nth(index)
            try:
                if await candidate.is_visible():
                    return candidate
            except Exception:
                pass

        normalized_label = " ".join(label.split()).strip().lower()
        if not normalized_label:
            return None

        for i in range(min(count, 80)):
            candidate = locator.nth(i)
            try:
                if not await candidate.is_visible():
                    continue
                text = " ".join(((await candidate.text_content()) or "").split()).strip().lower()
                aria = ((await candidate.get_attribute("aria-label")) or "").strip().lower()
                title = ((await candidate.get_attribute("title")) or "").strip().lower()
                haystack = " ".join(part for part in [text, aria, title] if part)
                if not haystack:
                    continue
                if haystack == normalized_label or normalized_label in haystack or haystack in normalized_label:
                    return candidate
            except Exception:
                continue
        return None

    async def execute_form_decision(self, decision: ActionDecision) -> StateSnapshot | None:
        current_target = self.engine.state.targets.get(self.engine.state.current_target_id or "")
        if not current_target:
            return None

        try:
            before = await self.engine._capture_runtime_signature()
            filled_count = await self.engine._fill_visible_form_fields()
            submit_selector = str(decision.metadata.get("submit_selector", "button[type='submit'], button, [role='button']"))
            submit_index = int(decision.metadata.get("submit_index", 0))
            submit_locator = self.engine.controller.page.locator(submit_selector)
            submit_count = await submit_locator.count()
            if submit_count <= submit_index:
                self.engine._remember_action_outcome(decision, False, "submit_index_out_of_range")
                return None
            button = submit_locator.nth(submit_index)
            if not await button.is_visible():
                self.engine._remember_action_outcome(decision, False, "submit_not_visible")
                return None
            if not await self.engine.controller.click_locator(
                button,
                wait=self.engine.config.crawl.wait_after_navigation / 1000,
            ):
                self.engine._remember_action_outcome(decision, False, "submit_click_failed")
                return None
            after = await self.engine._capture_runtime_signature()
            if self.engine.config.task.validate_action_outcomes and not self.engine._state_changed_meaningfully(before, after):
                self.engine.logger.log(
                    AgentPhase.EXECUTE,
                    "form_submit_no_effect",
                    decision.label,
                    "failed",
                    "no meaningful state change detected",
                )
                self.engine._remember_action_outcome(decision, False, "no_state_change")
                return None

            result = await self.capture_interaction(
                decision.label or "form_submit",
                current_target,
                "form_submit",
            )
            if result == "captured":
                self.engine._remember_action_outcome(decision, True, f"captured; filled_fields={filled_count}")
            elif result == "skipped_novelty":
                self.engine._remember_action_outcome(decision, True, f"state_changed_low_novelty; filled_fields={filled_count}")
            else:
                self.engine._remember_action_outcome(decision, False, f"{result}; filled_fields={filled_count}")
            if result != "captured":
                return None
            current_state_id = self.engine.state.current_state_id or ""
            self.engine.logger.log(
                AgentPhase.EXECUTE,
                "form_submitted",
                decision.label,
                "success",
                f"filled_fields={filled_count}",
            )
            return self.engine.state.states.get(current_state_id)
        except Exception as e:
            self.engine.logger.log(
                AgentPhase.EXECUTE,
                "form_submit_failed",
                decision.label,
                "failed",
                str(e),
            )
            self.engine._remember_action_outcome(decision, False, str(e))
            return None

    async def execute_route(self, target: ExplorationTarget) -> StateSnapshot | None:
        step = self.engine.state.next_step()
        console.print(f"\n[bold cyan]Step {step}: route -> {target.label}[/bold cyan]")

        success = False
        for attempt in range(1 + self.engine.config.budget.retry_limit):
            with self.engine.logger.timed(AgentPhase.EXECUTE, "navigate", target.label) as ctx:
                try:
                    success = await self.navigate_to_target(target)
                    if success:
                        ctx["reason"] = "navigation successful"
                        break
                    ctx["result"] = "retry" if attempt < self.engine.config.budget.retry_limit else "failed"
                    ctx["reason"] = f"attempt {attempt + 1} failed"
                except Exception as e:
                    ctx["result"] = "retry" if attempt < self.engine.config.budget.retry_limit else "failed"
                    ctx["reason"] = str(e)
            if not success and attempt < self.engine.config.budget.retry_limit:
                await asyncio.sleep(1)

        if not success:
            self.engine.state.mark_failed(target.id)
            self.engine._remember_action_outcome(
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

        if not await self.engine.authenticator.check_session():
            await self.engine.authenticator.re_login()
            return None

        snapshot = await self.capture_and_register(target)
        if snapshot:
            self.engine._remember_action_outcome(
                ActionDecision(
                    action_type=ActionType.NAVIGATE,
                    target_id=target.id,
                    label=target.label,
                    metadata={"selector": target.locator, "context": "route"},
                ),
                True,
                "captured_route",
            )
        if snapshot and self.engine.config.task.reobserve_on_state_change:
            await self.engine._reobserve_current_state(
                state_id=snapshot.id,
                current_url=snapshot.url,
                reason="route_capture",
                allow_vision=True,
                discover_candidates=False,
            )
        return snapshot

    async def explore_page_interactions(self, route_target: ExplorationTarget) -> None:
        page = self.engine.controller.page
        icfg = self.engine.config.interaction
        wait = self.engine.config.crawl.wait_after_navigation / 1000
        max_items = self.engine.config.crawl.max_interaction_items
        destructive = self.engine.config.exploration.destructive_keywords
        strict_dd_selector = self.engine.config.interaction.dropdown_item_strict_selector

        coverage = self.engine.state.coverage.get(route_target.id, PageCoverage())
        route_label = route_target.label

        console.print(f"[yellow]  Exploring interactions on: {route_label}[/yellow]")

        action_loc, action_count = await self.engine.controller.find_first_visible(icfg.action_button_selectors)
        if action_loc and action_count > 0:
            coverage.action_buttons_found = action_count
            console.print(f"[cyan]    Action buttons: {action_count} found[/cyan]")

            try:
                await self.engine.controller.click_locator(action_loc.first, wait=0.8)
                coverage.action_buttons_clicked += 1
                await self.capture_interaction("action_dropdown", route_target, "dropdown")

                items = page.locator(strict_dd_selector)
                item_count = await items.count()
                coverage.dropdown_items_found = item_count
                console.print(f"[cyan]    Dropdown items: {item_count} found[/cyan]")

                item_texts: list[tuple[int, str]] = []
                for i in range(min(item_count, max_items)):
                    try:
                        text = (await items.nth(i).text_content() or "").strip()
                        if text:
                            item_texts.append((i, text))
                    except Exception:
                        continue

                await self.engine.controller.close_overlays()

                for item_idx, item_text in item_texts:
                    if not self.engine.state.has_budget():
                        break
                    if any(kw.lower() in item_text.lower() for kw in destructive):
                        console.print(f"[dim]    Skipping destructive: {item_text}[/dim]")
                        continue

                    coverage.dropdown_item_labels.append(item_text)
                    console.print(f"[cyan]    Clicking dropdown item: {item_text}[/cyan]")

                    try:
                        await self.engine.controller.click_locator(action_loc.first, wait=0.5)
                        await asyncio.sleep(0.3)

                        fresh_items = page.locator(strict_dd_selector)
                        fresh_count = await fresh_items.count()
                        if item_idx >= fresh_count:
                            await self.engine.controller.close_overlays()
                            continue

                        await fresh_items.nth(item_idx).click()
                        await asyncio.sleep(wait)

                        label = f"{item_text}@{route_label}"
                        result = await self.capture_interaction(label, route_target, "dropdown_item")
                        if result == "captured":
                            coverage.dropdown_items_explored += 1
                        elif result == "skipped_novelty":
                            coverage.dropdown_items_skipped_novelty += 1

                        if await self.engine.controller.is_modal_open():
                            await self.engine.controller.close_overlays()
                        else:
                            current_url = await self.engine.controller.get_url()
                            if self.engine._normalize_url(current_url) != self.engine._normalize_url(
                                await self.get_route_url(route_target)
                            ):
                                await self.engine.controller.go_back()
                                await asyncio.sleep(wait)

                    except Exception as e:
                        console.print(f"[dim]    Failed: {item_text} ({e})[/dim]")
                        await self.engine.controller.close_overlays()

            except Exception as e:
                console.print(f"[dim]    Action dropdown failed: {e}[/dim]")
                await self.engine.controller.close_overlays()

        add_loc, _ = await self.engine.controller.find_first_visible(icfg.add_button_selectors)
        if add_loc:
            coverage.add_buttons_found += 1
            try:
                add_text = (await add_loc.first.text_content() or "add").strip()
                console.print(f"[cyan]    Add button: {add_text}[/cyan]")
                await self.engine.controller.click_locator(add_loc.first, wait=wait)

                label = f"add_form_{add_text}@{route_label}"
                result = await self.capture_interaction(label, route_target, "modal")
                if result == "captured":
                    coverage.add_buttons_clicked += 1
                elif result == "skipped_novelty":
                    coverage.add_buttons_skipped_novelty += 1

                await self.engine.controller.close_overlays()
            except Exception as e:
                console.print(f"[dim]    Add button failed: {e}[/dim]")
                await self.engine.controller.close_overlays()

        expand_loc, expand_count = await self.engine.controller.find_first_visible(icfg.expand_selectors)
        if expand_loc and expand_count > 0:
            coverage.expand_rows_found = expand_count
            try:
                console.print(f"[cyan]    Expandable rows: {expand_count} found[/cyan]")
                await self.engine.controller.click_locator(expand_loc.first, wait=1.0)

                label = f"expand_row@{route_label}"
                result = await self.capture_interaction(label, route_target, "expanded_row")
                if result == "captured":
                    coverage.expand_rows_expanded += 1
                elif result == "skipped_novelty":
                    coverage.expand_rows_skipped_novelty += 1
            except Exception:
                pass

        try:
            tabs = page.locator(icfg.tab_selector)
            tab_count = await tabs.count()
            if tab_count > 0:
                coverage.tabs_found = tab_count
                console.print(f"[cyan]    Tabs: {tab_count} found[/cyan]")
                for i in range(min(tab_count, 4)):
                    if not self.engine.state.has_budget():
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
                        result = await self.capture_interaction(label, route_target, "tab_state")
                        if result == "captured":
                            coverage.tabs_switched += 1
                        elif result == "skipped_novelty":
                            coverage.tabs_skipped_novelty += 1
                    except Exception:
                        continue
        except Exception:
            pass

        if route_target.id in self.engine.state.coverage:
            self.engine.state.coverage[route_target.id] = coverage

    async def capture_interaction(self, label: str, parent_target: ExplorationTarget, context: str) -> str:
        if not self.engine.state.has_budget():
            return "skipped_budget"

        html = await self.engine.controller.get_html()
        novelty, fingerprint = self.engine.novelty_scorer.score(html)
        threshold = self.engine.config.budget.novelty_threshold

        if novelty < threshold:
            self.engine.novelty_scorer.register(html, fingerprint)
            console.print(f"[dim]    Low novelty ({novelty:.2f}) - skipped[/dim]")
            self.engine.logger.log(
                AgentPhase.EVAL_NOVELTY,
                "skip_interaction",
                label,
                "skipped",
                f"novelty={novelty:.2f}",
            )
            return "skipped_novelty"

        url = await self.engine.controller.get_url()
        title = await self.engine.controller.get_title()
        screenshot_path = await self.engine.controller.capture_screenshot(label, context)
        report_screenshot_path = ""
        if self.engine.config.run.capture_report_screenshots:
            report_screenshot_path = await self.capture_report_screenshot(
                label,
                context,
                prefer_full_page=False,
            )
        html_path = await self.engine.controller.save_html(label, context)

        snapshot = StateSnapshot.create(
            target_id=parent_target.id,
            url=url,
            title=title,
            screenshot_path=screenshot_path,
            html_path=html_path,
            visit_status=VisitStatus.SUCCESS,
            depth=parent_target.depth + 1,
            novelty_score=novelty,
            dom_fingerprint=fingerprint,
            metadata={
                "capture_label": label,
                "capture_context": context,
                "report_screenshot_path": report_screenshot_path,
            },
        )
        self.engine.state.register_state(snapshot)
        self.engine.state.consume_budget()
        self.engine.novelty_scorer.register(html, fingerprint)
        self.engine.state.current_state_id = snapshot.id

        if html:
            computed_styles = await self.engine.controller.get_computed_styles()
            analysis = self.engine.analyzer.analyze(html, computed_styles)
            self.engine._analysis_results[snapshot.id] = analysis
            self.engine.artifacts.save_analysis(snapshot.id, analysis)
        if self.engine.config.task.reobserve_on_state_change:
            await self.engine._reobserve_current_state(
                state_id=snapshot.id,
                current_url=url,
                reason=context,
                allow_vision=self.engine.config.task.use_vision_on_state_change,
                discover_candidates=False,
            )
        if self.engine.config.run.enable_extraction:
            await self.run_extraction(
                snapshot,
                capture_label=label,
                capture_context=context,
                allow_vision=self.engine.config.task.use_vision_on_state_change,
            )

        self.engine.logger.log(
            AgentPhase.EXECUTE,
            f"capture_{context}",
            label,
            "success",
            f"novelty={novelty:.2f}",
        )
        console.print(f"[green]    Captured: {url} (novelty={novelty:.2f})[/green]")
        return "captured"

    async def capture_report_screenshot(self, label: str, context: str, prefer_full_page: bool) -> str:
        if prefer_full_page:
            return await self.engine.controller.capture_screenshot(label, f"{context}_report")
        return await self.engine.controller.capture_viewport_screenshot(label, f"{context}_report")

    async def phase_analyze(self, snapshot: StateSnapshot) -> None:
        self.engine.state.phase = AgentPhase.ANALYZE

        html = ""
        try:
            html_path = Path(snapshot.html_path)
            if html_path.exists():
                html = html_path.read_text(encoding="utf-8")
        except Exception:
            return

        if not html:
            return

        with self.engine.logger.timed(AgentPhase.ANALYZE, "analyze_page", snapshot.id) as ctx:
            computed_styles = await self.engine.controller.get_computed_styles()
            analysis = self.engine.analyzer.analyze(html, computed_styles)
            self.engine._analysis_results[snapshot.id] = analysis
            self.engine.artifacts.save_analysis(snapshot.id, analysis)
            ctx["reason"] = f"components: {', '.join(analysis.get('component_types', []))}"

    async def run_extraction(
        self,
        snapshot: StateSnapshot,
        capture_label: str = "",
        capture_context: str = "",
        allow_vision: bool = True,
    ) -> None:
        html = ""
        try:
            html_path = Path(snapshot.html_path)
            if html_path.exists():
                html = html_path.read_text(encoding="utf-8")
        except Exception:
            html = ""

        if not html:
            return

        if snapshot.id not in self.engine._page_insights:
            dom_summary = await self.engine._build_dom_summary()
            vision_result = (
                await self.engine._understand_current_page(snapshot.url, dom_summary)
                if allow_vision else VisionResult()
            )
            insight_obj = self.engine._build_page_insight(
                snapshot.url,
                dom_summary,
                vision_result,
                state_id=snapshot.id,
            )
            self.engine._persist_page_understanding(insight_obj, vision_result)

        insight = self.engine._page_insights.get(snapshot.id) or {}
        strategy = str(insight.get("extraction_strategy", "unknown"))
        page_type = self.engine._resolved_page_type(insight)

        evidence_paths = EvidencePaths(
            screenshot=snapshot.screenshot_path,
            html=snapshot.html_path,
        )

        result = self.engine.extraction.extract(
            html=html,
            state_id=snapshot.id,
            target_id=snapshot.target_id,
            url=snapshot.url,
            page_type=page_type,
            strategy=strategy,
            evidence_paths=evidence_paths,
            page_insight=insight,
            vision_result=self.engine._vision_results.get(snapshot.id),
        )
        result.capture_label = capture_label
        result.capture_context = capture_context
        self.engine._extraction_results[snapshot.id] = result.model_dump()

    async def navigate_to_target(self, target: ExplorationTarget) -> bool:
        locator = target.locator
        url_before = await self.engine.controller.get_url()

        if locator.startswith(("http://", "https://", "#", "/")):
            url = locator
            if locator.startswith(("#", "/")):
                parsed = urlparse(url_before)
                if locator.startswith("#"):
                    url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}{locator}"
                else:
                    url = f"{parsed.scheme}://{parsed.netloc}{locator}"
            return await self.engine.controller.goto(url)

        clicked = await self.engine.controller.click(
            locator,
            timeout=self.engine.config.crawl.interaction_timeout,
        )
        if clicked:
            url_after = await self.engine.controller.get_url()
            if url_after == url_before:
                return False
        return clicked

    async def capture_and_register(self, target: ExplorationTarget) -> StateSnapshot | None:
        try:
            url = await self.engine.controller.get_url()
            title = await self.engine.controller.get_title()
            label = target.label or self.engine._url_to_label(url)

            html = await self.engine.controller.get_html()
            novelty, fingerprint = self.engine.novelty_scorer.score(html)
            self.engine.novelty_scorer.register(html, fingerprint)

            screenshot_path = await self.engine.controller.capture_screenshot(
                label,
                "route",
                full_page=(target.depth == 0),
            )
            report_screenshot_path = ""
            if self.engine.config.run.capture_report_screenshots:
                report_screenshot_path = await self.capture_report_screenshot(
                    label,
                    "route",
                    prefer_full_page=(target.depth == 0),
                )
            html_path = await self.engine.controller.save_html(label, "route")

            snapshot = StateSnapshot.create(
                target_id=target.id,
                url=url,
                title=title,
                screenshot_path=screenshot_path,
                html_path=html_path,
                visit_status=VisitStatus.SUCCESS,
                depth=target.depth,
                novelty_score=novelty,
                dom_fingerprint=fingerprint,
                metadata={
                    "capture_label": label,
                    "capture_context": "route",
                    "report_screenshot_path": report_screenshot_path,
                },
            )

            self.engine.state.register_state(snapshot)
            self.engine.state.mark_visited(target.id)
            self.engine.state.consume_budget()
            self.engine.state.current_state_id = snapshot.id
            self.engine.state.current_target_id = target.id

            console.print(f"[green]  Captured: {url} (novelty={novelty:.2f})[/green]")
            return snapshot

        except Exception as e:
            self.engine.logger.log(
                AgentPhase.EXECUTE,
                "capture_route_failed",
                target.label,
                "failed",
                str(e),
            )
            console.print(f"[red]  Capture failed: {e}[/red]")
            return None

    async def get_route_url(self, route_target: ExplorationTarget) -> str:
        locator = route_target.locator
        if locator.startswith(("http://", "https://")):
            return locator
        if locator.startswith(("#", "/")):
            base = self.engine.config.target.url
            parsed = urlparse(base)
            if locator.startswith("#"):
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}{locator}"
            return f"{parsed.scheme}://{parsed.netloc}{locator}"
        return locator
