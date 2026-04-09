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

    def _is_low_value_nav_label(self, label: str) -> bool:
        normalized = " ".join(label.lower().split())
        if normalized in {
            "skip to content",
            "close",
            "menu",
            "smaller",
            "larger",
            "back to top",
        }:
            return True
        if normalized.replace(" ", "") in {"aa", "aaa"}:
            return True
        return False

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

    def _route_priority(self, label: str, href: str, region: str, context: str) -> int:
        """Heuristic score for prioritizing public route candidates."""
        label_lower = " ".join(label.lower().split())
        href_lower = href.lower()
        score = 0

        if region == "nav":
            score += 3
        elif region == "main":
            score += 4
        elif region == "footer":
            score -= 1

        if context in {"table", "card", "section"}:
            score += 2

        for hint in self.config.exploration.high_value_path_hints:
            if hint in href_lower or hint in label_lower:
                score += 4

        for hint in self.config.exploration.low_value_path_hints:
            if hint in href_lower or hint in label_lower:
                score -= 4

        if any(token in href_lower for token in ["/login", "/signin", "/signup", "/register"]):
            score += 1

        return score

    def _is_viable_route_candidate(self, page_url: str, label: str, href: str) -> bool:
        """Filter out low-value or off-site routes before entering the frontier."""
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
        if any(hint in href_lower for hint in self.config.exploration.low_value_path_hints):
            return False
        if any(kw.lower() in label_lower for kw in self.config.exploration.destructive_keywords):
            return False
        if any(token in label_lower for token in ["logout", "sign out", "log out", "delete", "remove"]):
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
        """Extract navigation menu items (sidebar, nav bar) as route targets."""
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
                            ExplorationTarget.create(
                                target_type=TargetType.ROUTE,
                                locator=absolute_href,
                                label=label,
                                parent_id=parent_id,
                                depth=depth + 1,
                                discovery_method="nav_menu",
                                metadata={
                                    "href": absolute_href,
                                    "original_selector": selector,
                                    "region": "nav",
                                    "context": "nav",
                                    "priority": self._route_priority(label, absolute_href, "nav", "nav"),
                                },
                            )
                        )
                    except Exception:
                        continue
            except Exception:
                continue

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

        ranked_candidates: list[tuple[int, str, str, str, str]] = []
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

                if not self._is_viable_route_candidate(page.url, label, href):
                    continue
                if href in seen_hrefs or label in seen_labels:
                    continue

                seen_hrefs.add(href)
                seen_labels.add(label)
                ranked_candidates.append((self._route_priority(label, href, region, context), href, label, region, context))
            except Exception:
                continue

        ranked_candidates.sort(key=lambda item: (-item[0], item[2].lower(), item[1]))
        for priority, href, label, region, context in ranked_candidates[: self.config.exploration.max_route_candidates_per_page]:
            targets.append(
                ExplorationTarget.create(
                    target_type=TargetType.ROUTE,
                    locator=href,
                    label=label,
                    parent_id=parent_id,
                    depth=depth + 1,
                    discovery_method="internal_link",
                    metadata={
                        "href": href,
                        "region": region,
                        "context": context,
                        "priority": priority,
                        "original_selector": "document.querySelectorAll('a[href]')",
                    },
                )
            )

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
