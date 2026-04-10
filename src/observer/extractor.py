"""Candidate extractor - detects interactive targets on the current page."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page
from rich.console import Console

from src.agent.state import ExplorationTarget, PageCoverage, TargetType
from src.config import AppConfig

console = Console()


class CandidateExtractor:
    """Find candidate navigation and interaction targets on the current page."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._seen_hover_nav_signatures: set[str] = set()

    def _is_low_value_nav_label(self, label: str) -> bool:
        normalized = " ".join(label.lower().split())
        return not normalized

    def _is_low_value_nav_href(self, href: str) -> bool:
        normalized = href.strip().lower()
        if not normalized:
            return True
        if normalized in {"#", "javascript:;"}:
            return True
        if normalized.startswith("#"):
            return True
        return False

    def _normalize_href(self, page_url: str, href: str) -> str:
        """Resolve a discovered href to an absolute URL without fragments."""
        absolute = urljoin(page_url, href or "").strip()
        if "#" in absolute:
            absolute = absolute.split("#", 1)[0]
        return absolute

    def _is_same_site_href(self, page_url: str, href: str) -> bool:
        """Keep route discovery on the current site only."""
        parsed_page = urlparse(page_url)
        parsed_href = urlparse(self._normalize_href(page_url, href))
        if parsed_href.scheme not in {"http", "https"}:
            return False
        return parsed_href.netloc == parsed_page.netloc

    def _derive_label_from_href(self, href: str) -> str:
        """Fallback label derived from the last path segment."""
        path = urlparse(href).path.strip("/")
        if not path:
            return "Home"
        segment = path.split("/")[-1].replace("-", " ").replace("_", " ").strip()
        return segment[:80] if segment else "Route"

    def _normalize_label(self, label: str) -> str:
        return " ".join(label.split()).strip()

    def _route_defer_reason(self, label: str, href: str, region: str) -> str:
        return ""

    def _nav_signature(self, targets: list[ExplorationTarget]) -> str:
        parts = sorted(
            f"{target.label.lower()}::{target.locator.lower()}"
            for target in targets
        )
        return "|".join(parts[:12])

    def _make_route_target(
        self,
        page_url: str,
        href: str,
        label: str,
        parent_id: str | None,
        depth: int,
        discovery_method: str,
        region: str,
        context: str,
        original_selector: str,
        hover_path: list[str] | None = None,
    ) -> ExplorationTarget:
        normalized_href = self._normalize_href(page_url, href)
        normalized_label = self._normalize_label(label)
        return ExplorationTarget.create(
            target_type=TargetType.ROUTE,
            locator=normalized_href,
            label=normalized_label,
            parent_id=parent_id,
            depth=depth + 1,
            discovery_method=discovery_method,
            metadata={
                "href": normalized_href,
                "region": region,
                "context": context,
                "original_selector": original_selector,
                "hover_path": list(hover_path or []),
            },
        )

    async def _collect_hover_trigger_specs(
        self,
        page: Page,
        selectors: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        seen: set[str] = set()

        for selector in selectors:
            try:
                loc = page.locator(selector)
                count = await loc.count()
            except Exception:
                continue

            for idx in range(min(count, limit * 3)):
                try:
                    item = loc.nth(idx)
                    if not await item.is_visible():
                        continue
                    text = await item.text_content() or ""
                    aria_label = await item.get_attribute("aria-label") or ""
                    title = await item.get_attribute("title") or ""
                    label = self._normalize_label(text or aria_label or title)
                    if not label or len(label) > 60 or self._is_low_value_nav_label(label):
                        continue
                    href = await item.get_attribute("href") or ""
                    key = f"{selector}|{idx}|{label.lower()}|{href.lower()}"
                    if key in seen:
                        continue
                    seen.add(key)
                    specs.append(
                        {
                            "selector": selector,
                            "index": idx,
                            "label": label,
                            "href": href,
                        }
                    )
                    if len(specs) >= limit:
                        return specs
                except Exception:
                    continue
        return specs

    async def _hover_over_trigger(self, page: Page, selector: str, index: int) -> bool:
        try:
            target = page.locator(selector).nth(index)
            if not await target.is_visible():
                return False
            await target.hover()
            await page.wait_for_timeout(self.config.exploration.hover_menu_wait_ms)
            return True
        except Exception:
            return False

    async def _reset_hover_state(self, page: Page) -> None:
        try:
            await page.mouse.move(5, 5)
            await page.wait_for_timeout(120)
        except Exception:
            pass

    async def _collect_hover_revealed_routes(
        self,
        page: Page,
        parent_id: str | None,
        depth: int,
        seen_hrefs: set[str],
        seen_labels: set[str],
        hover_path: list[str],
    ) -> list[ExplorationTarget]:
        routes: list[ExplorationTarget] = []
        try:
            anchors = await self._collect_anchor_candidates(page)
        except Exception:
            return routes

        revealed: list[tuple[str, str, str, str]] = []
        for anchor in anchors:
            try:
                if not bool(anchor.get("visible")):
                    continue
                href = str(anchor.get("hrefResolved") or anchor.get("hrefAttr") or "").strip()
                href = self._normalize_href(page.url, href)
                label = str(anchor.get("text") or anchor.get("ariaLabel") or anchor.get("title") or "").strip()
                if not label:
                    label = self._derive_label_from_href(href)
                label = self._normalize_label(label)
                if not label or len(label) > 80:
                    continue

                region = str(anchor.get("region") or "other")
                context = str(anchor.get("context") or "other")
                if region == "main":
                    continue
                if not self._is_viable_route_candidate(page.url, label, href):
                    continue
                if href in seen_hrefs or label in seen_labels:
                    continue

                revealed.append((href, label, region, context))
                seen_hrefs.add(href)
                seen_labels.add(label)
            except Exception:
                continue

        for href, label, region, context in revealed[: self.config.exploration.max_route_candidates_per_page]:
            target = self._make_route_target(
                page_url=page.url,
                href=href,
                label=label,
                parent_id=parent_id,
                depth=depth,
                discovery_method="hover_menu",
                region=region,
                context=context,
                original_selector="hover_menu",
                hover_path=hover_path,
            )
            routes.append(target)
        return routes

    async def _explore_hover_menu_routes(
        self,
        page: Page,
        parent_id: str | None,
        depth: int,
        seen_hrefs: set[str],
        seen_labels: set[str],
        selectors: list[str],
        current_depth: int,
        hover_path: list[str] | None = None,
    ) -> list[ExplorationTarget]:
        routes: list[ExplorationTarget] = []
        if current_depth > self.config.exploration.hover_menu_max_depth:
            return routes

        hover_path = list(hover_path or [])
        trigger_specs = await self._collect_hover_trigger_specs(
            page,
            selectors,
            self.config.exploration.hover_menu_max_triggers,
        )
        for spec in trigger_specs:
            next_path = hover_path + [str(spec["label"])]
            if not await self._hover_over_trigger(page, str(spec["selector"]), int(spec["index"])):
                continue
            routes.extend(
                await self._collect_hover_revealed_routes(
                    page,
                    parent_id,
                    depth,
                    seen_hrefs,
                    seen_labels,
                    next_path,
                )
            )
            routes.extend(
                await self._explore_hover_menu_routes(
                    page,
                    parent_id,
                    depth,
                    seen_hrefs,
                    seen_labels,
                    self.config.exploration.hover_menu_nested_selectors,
                    current_depth + 1,
                    next_path,
                )
            )
            await self._reset_hover_state(page)

        return routes

    async def _top_nav_signature(self, page: Page) -> str:
        specs = await self._collect_hover_trigger_specs(
            page,
            self.config.exploration.hover_menu_trigger_selectors,
            self.config.exploration.hover_menu_max_triggers,
        )
        parts = sorted(
            f"{self._normalize_label(str(spec['label'])).lower()}::{self._normalize_href(page.url, str(spec.get('href') or ''))}"
            for spec in specs
        )
        return "|".join(parts[:12])

    def _route_priority(self, label: str, href: str, region: str, context: str) -> int:
        """Route priority is no longer heuristic-driven."""
        return 0

    def _is_viable_route_candidate(self, page_url: str, label: str, href: str) -> bool:
        """Keep only mechanically executable same-site routes."""
        href_lower = href.lower()
        label_lower = label.lower()

        if not self._is_same_site_href(page_url, href):
            return False
        if any(pat in href_lower for pat in self.config.exploration.skip_patterns):
            return False
        if self._is_low_value_nav_label(label):
            return False
        if self._is_low_value_nav_href(href):
            return False
        if any(kw.lower() in label_lower for kw in self.config.exploration.destructive_keywords):
            return False
        return True

    async def _expand_submenus(self, page: Page) -> None:
        """Expand collapsed sub-menus so leaf items become visible."""
        for selector in self.config.exploration.submenu_expand_selectors:
            try:
                submenus = page.locator(selector)
                count = await submenus.count()
                for i in range(min(count, 8)):
                    try:
                        item = submenus.nth(i)
                        if await item.is_visible():
                            await item.click()
                            await page.wait_for_timeout(300)
                    except Exception:
                        continue
            except Exception:
                continue

    async def _collect_anchor_candidates(self, page: Page) -> list[dict[str, Any]]:
        """Collect visible anchor metadata across the page in one DOM pass."""
        return await page.evaluate(
            """
            () => {
              const isVisible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                if (!rect.width || !rect.height) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                if (el.closest('[hidden], [aria-hidden="true"]')) return false;
                return true;
              };

              return Array.from(document.querySelectorAll('a[href]')).map((el) => {
                const rect = el.getBoundingClientRect();
                const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                const ariaLabel = (el.getAttribute('aria-label') || '').trim();
                const title = (el.getAttribute('title') || '').trim();

                let region = 'other';
                if (el.closest('nav, header, [role="navigation"], .navbar, .sidebar, .side-nav')) {
                  region = 'nav';
                } else if (el.closest('main, [role="main"], article')) {
                  region = 'main';
                } else if (el.closest('footer')) {
                  region = 'footer';
                }

                let context = 'other';
                if (el.closest('table, [role="table"], [class*="table"]')) {
                  context = 'table';
                } else if (el.closest('.card, [class*="card"], [class*="tile"], [class*="panel"], [class*="benchmark"], [class*="leaderboard"]')) {
                  context = 'card';
                } else if (el.closest('section')) {
                  context = 'section';
                } else if (el.closest('ul, ol')) {
                  context = 'list';
                }

                return {
                  hrefAttr: el.getAttribute('href') || '',
                  hrefResolved: el.href || '',
                  text,
                  ariaLabel,
                  title,
                  visible: isVisible(el),
                  region,
                  context,
                  top: rect.top,
                  left: rect.left
                };
              });
            }
            """
        )

    async def extract_nav_targets(self, page: Page, parent_id: str | None, depth: int) -> list[ExplorationTarget]:
        """Extract navigation menu items, caching only the expensive hover pass."""
        top_nav_signature = await self._top_nav_signature(page)
        should_run_hover_discovery = bool(top_nav_signature)
        if top_nav_signature and top_nav_signature in self._seen_hover_nav_signatures:
            should_run_hover_discovery = False
        elif top_nav_signature:
            self._seen_hover_nav_signatures.add(top_nav_signature)

        await self._expand_submenus(page)

        targets: list[ExplorationTarget] = []
        seen_hrefs: set[str] = set()
        seen_labels: set[str] = set()

        for selector in self.config.exploration.nav_selectors:
            try:
                elements = page.locator(selector)
                count = await elements.count()
                for i in range(count):
                    el = elements.nth(i)
                    try:
                        if not await el.is_visible():
                            continue

                        label = " ".join(((await el.text_content()) or "").split()).strip()
                        if not label or len(label) > 80:
                            continue

                        href = ""
                        for attr in ["href", "to", "data-href"]:
                            href = await el.get_attribute(attr) or ""
                            if href:
                                break

                        if not href:
                            try:
                                child_a = el.locator("a[href]").first
                                if await child_a.count() > 0:
                                    href = await child_a.get_attribute("href") or ""
                            except Exception:
                                pass

                        if not href:
                            tag_name = await el.evaluate("node => node.tagName.toLowerCase()")
                            if tag_name != "a":
                                continue

                        absolute_href = self._normalize_href(page.url, href)
                        if not self._is_viable_route_candidate(page.url, label, absolute_href):
                            continue

                        if absolute_href in seen_hrefs or label in seen_labels:
                            continue
                        seen_hrefs.add(absolute_href)
                        seen_labels.add(label)

                        targets.append(
                            self._make_route_target(
                                page_url=page.url,
                                href=absolute_href,
                                label=label,
                                parent_id=parent_id,
                                depth=depth,
                                discovery_method="nav_menu",
                                region="nav",
                                context="nav",
                                original_selector=selector,
                            )
                        )
                    except Exception:
                        continue
            except Exception:
                continue

        if should_run_hover_discovery:
            targets.extend(
                await self._explore_hover_menu_routes(
                    page,
                    parent_id,
                    depth,
                    seen_hrefs,
                    seen_labels,
                    self.config.exploration.hover_menu_trigger_selectors,
                    current_depth=1,
                )
            )
        return targets

    async def extract_internal_link_targets(self, page: Page, parent_id: str | None, depth: int) -> list[ExplorationTarget]:
        """Extract visible same-site links across the page, not just inside nav."""
        targets: list[ExplorationTarget] = []
        seen_hrefs: set[str] = set()
        seen_labels: set[str] = set()

        try:
            anchors = await self._collect_anchor_candidates(page)
        except Exception:
            return targets

        ordered_candidates: list[tuple[str, str, str, str]] = []
        for anchor in anchors:
            try:
                if not bool(anchor.get("visible")):
                    continue

                href = str(anchor.get("hrefResolved") or anchor.get("hrefAttr") or "").strip()
                href = self._normalize_href(page.url, href)
                label = str(anchor.get("text") or anchor.get("ariaLabel") or anchor.get("title") or "").strip()
                if not label:
                    label = self._derive_label_from_href(href)
                label = " ".join(label.split()).strip()
                if not label or len(label) > 80:
                    continue

                region = str(anchor.get("region") or "other")
                context = str(anchor.get("context") or "other")

                if region == "nav":
                    continue

                if not self._is_viable_route_candidate(page.url, label, href):
                    continue
                if href in seen_hrefs or label in seen_labels:
                    continue

                seen_hrefs.add(href)
                seen_labels.add(label)
                ordered_candidates.append((href, label, region, context))
            except Exception:
                continue

        for href, label, region, context in ordered_candidates[: self.config.exploration.max_route_candidates_per_page]:
            target = self._make_route_target(
                page_url=page.url,
                href=href,
                label=label,
                parent_id=parent_id,
                depth=depth,
                discovery_method="internal_link",
                region=region,
                context=context,
                original_selector="document.querySelectorAll('a[href]')",
            )
            targets.append(target)

        return targets

    async def extract_action_targets(self, page: Page, parent_id: str | None, depth: int) -> list[ExplorationTarget]:
        """Extract action buttons (Actions dropdowns) as interaction targets."""
        targets = []
        icfg = self.config.interaction

        for selector in icfg.action_button_selectors:
            try:
                loc = page.locator(selector)
                count = await loc.count()
                if count > 0 and await loc.first.is_visible():
                    page_label = parent_id or "root"
                    targets.append(
                        ExplorationTarget.create(
                            target_type=TargetType.DROPDOWN,
                            locator=selector,
                            label=f"action_dropdown@{page_label}",
                            parent_id=parent_id,
                            depth=depth + 1,
                            discovery_method="action_button",
                            metadata={"button_count": count},
                        )
                    )
                    break
            except Exception:
                continue

        return targets

    async def extract_add_button_targets(self, page: Page, parent_id: str | None, depth: int) -> list[ExplorationTarget]:
        """Extract add/create buttons that open modals."""
        targets = []
        icfg = self.config.interaction

        for selector in icfg.add_button_selectors:
            try:
                loc = page.locator(selector)
                if await loc.count() > 0 and await loc.first.is_visible():
                    label = (await loc.first.text_content() or "add").strip()
                    page_label = parent_id or "root"
                    targets.append(
                        ExplorationTarget.create(
                            target_type=TargetType.MODAL,
                            locator=selector,
                            label=f"add_form_{label}@{page_label}",
                            parent_id=parent_id,
                            depth=depth + 1,
                            discovery_method="add_button",
                        )
                    )
                    break
            except Exception:
                continue

        return targets

    async def extract_tab_targets(self, page: Page, parent_id: str | None, depth: int) -> list[ExplorationTarget]:
        """Extract inactive tab elements."""
        targets = []
        icfg = self.config.interaction

        try:
            tabs = page.locator(icfg.tab_selector)
            count = await tabs.count()
            for i in range(min(count, 4)):
                try:
                    tab = tabs.nth(i)
                    if not await tab.is_visible():
                        continue
                    label = (await tab.text_content() or "").strip()
                    if not label:
                        continue
                    page_label = parent_id or "root"
                    targets.append(
                        ExplorationTarget.create(
                            target_type=TargetType.TAB_STATE,
                            locator=f"{icfg.tab_selector} >> nth={i}",
                            label=f"tab_{label}@{page_label}",
                            parent_id=parent_id,
                            depth=depth + 1,
                            discovery_method="tab_bar",
                            metadata={"tab_index": i, "tab_text": label},
                        )
                    )
                except Exception:
                    continue
        except Exception:
            pass

        return targets

    async def extract_expand_targets(self, page: Page, parent_id: str | None, depth: int) -> list[ExplorationTarget]:
        """Extract expandable table rows."""
        targets = []
        icfg = self.config.interaction

        for selector in icfg.expand_selectors:
            try:
                loc = page.locator(selector)
                count = await loc.count()
                if count > 0 and await loc.first.is_visible():
                    page_label = parent_id or "root"
                    targets.append(
                        ExplorationTarget.create(
                            target_type=TargetType.EXPANDED_ROW,
                            locator=selector,
                            label=f"expand_row@{page_label}",
                            parent_id=parent_id,
                            depth=depth + 1,
                            discovery_method="table_expand",
                            metadata={"expand_count": count},
                        )
                    )
                    break
            except Exception:
                continue

        return targets

    async def extract_all(self, page: Page, parent_id: str | None, depth: int) -> tuple[list[ExplorationTarget], PageCoverage]:
        """Extract all candidate targets from current page. Returns (targets, coverage)."""
        all_targets = []
        coverage = PageCoverage(
            page_url=page.url,
            page_label=parent_id or "root",
            target_id=parent_id or "",
        )

        nav = await self.extract_nav_targets(page, parent_id, depth)
        internal_links = await self.extract_internal_link_targets(page, parent_id, depth)
        all_targets.extend(nav)
        all_targets.extend(internal_links)
        coverage.nav_items_found = len(nav) + len(internal_links)

        actions = await self.extract_action_targets(page, parent_id, depth)
        all_targets.extend(actions)

        for selector in self.config.interaction.action_button_selectors:
            try:
                loc = page.locator(selector)
                count = await loc.count()
                if count > 0 and await loc.first.is_visible():
                    coverage.action_buttons_found = count
                    break
            except Exception:
                continue

        try:
            dropdown_items = page.locator(self.config.interaction.dropdown_item_selector)
            di_count = await dropdown_items.count()
            if di_count > 0:
                labels = []
                for i in range(min(di_count, 10)):
                    try:
                        text = (await dropdown_items.nth(i).text_content() or "").strip()
                        if text:
                            labels.append(text)
                    except Exception:
                        continue
                coverage.dropdown_items_found = di_count
                coverage.dropdown_item_labels = labels
        except Exception:
            pass

        add_btns = await self.extract_add_button_targets(page, parent_id, depth)
        all_targets.extend(add_btns)
        coverage.add_buttons_found = len(add_btns)

        tabs = await self.extract_tab_targets(page, parent_id, depth)
        all_targets.extend(tabs)
        coverage.tabs_found = len(tabs)
        coverage.tab_labels = [t.metadata.get("tab_text", "") for t in tabs if t.metadata.get("tab_text")]

        expands = await self.extract_expand_targets(page, parent_id, depth)
        all_targets.extend(expands)
        if expands:
            coverage.expand_rows_found = expands[0].metadata.get("expand_count", 0)

        return all_targets, coverage
