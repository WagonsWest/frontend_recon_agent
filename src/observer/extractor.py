"""Candidate extractor — detects interactive targets on the current page."""

from __future__ import annotations

from playwright.async_api import Page
from rich.console import Console

from src.config import AppConfig
from src.agent.state import ExplorationTarget, TargetType, PageCoverage

console = Console()


class CandidateExtractor:
    """Finds candidate navigation/interaction targets on the current page."""

    def __init__(self, config: AppConfig):
        self.config = config

    async def _expand_submenus(self, page: Page) -> None:
        """Expand collapsed sub-menus so leaf items become visible."""
        for selector in self.config.exploration.submenu_expand_selectors:
            try:
                submenus = page.locator(selector)
                count = await submenus.count()
                for i in range(count):
                    try:
                        item = submenus.nth(i)
                        if await item.is_visible():
                            await item.click()
                            await page.wait_for_timeout(300)
                    except Exception:
                        continue
            except Exception:
                continue

    async def extract_nav_targets(self, page: Page, parent_id: str | None, depth: int) -> list[ExplorationTarget]:
        """Extract navigation menu items (sidebar, nav bar) as route targets."""
        # First expand any collapsed sub-menus
        await self._expand_submenus(page)

        targets = []
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

                        label = (await el.text_content() or "").strip()
                        if not label or len(label) > 50:
                            continue

                        # Skip destructive items
                        if any(kw.lower() in label.lower() for kw in self.config.exploration.destructive_keywords):
                            continue
                        if any(pat in label.lower() for pat in ["logout", "登出", "退出"]):
                            continue

                        # Get href — try multiple attributes
                        href = ""
                        for attr in ["href", "to", "data-href"]:
                            href = await el.get_attribute(attr) or ""
                            if href:
                                break

                        # If no href on the element itself, check child <a> tags
                        if not href:
                            try:
                                child_a = el.locator("a[href]").first
                                if await child_a.count() > 0:
                                    href = await child_a.get_attribute("href") or ""
                            except Exception:
                                pass

                        # Skip if no href and not a direct link — it's likely a sub-menu toggle
                        if not href:
                            tag_name = await el.evaluate("el => el.tagName.toLowerCase()")
                            if tag_name != "a":
                                continue

                        # Skip excluded patterns
                        if any(pat in href for pat in self.config.exploration.skip_patterns):
                            continue

                        # Dedup by href
                        if href and href in seen_hrefs:
                            continue
                        if href:
                            seen_hrefs.add(href)

                        # Dedup by label
                        if label in seen_labels:
                            continue
                        seen_labels.add(label)

                        # Prefer href-based navigation
                        locator = href if href and href.startswith(("http", "#", "/")) else f"{selector} >> nth={i}"

                        target = ExplorationTarget.create(
                            target_type=TargetType.ROUTE,
                            locator=locator,
                            label=label,
                            parent_id=parent_id,
                            depth=depth + 1,
                            discovery_method="nav_menu",
                            metadata={"href": href, "original_selector": selector},
                        )
                        targets.append(target)
                    except Exception:
                        continue
            except Exception:
                continue

        return targets

    async def extract_action_targets(self, page: Page, parent_id: str | None, depth: int) -> list[ExplorationTarget]:
        """Extract action buttons (操作/Actions dropdowns) as interaction targets."""
        targets = []
        icfg = self.config.interaction

        for selector in icfg.action_button_selectors:
            try:
                loc = page.locator(selector)
                count = await loc.count()
                if count > 0 and await loc.first.is_visible():
                    # Use parent_id in label to make it unique per page
                    page_label = parent_id or "root"
                    target = ExplorationTarget.create(
                        target_type=TargetType.DROPDOWN,
                        locator=selector,
                        label=f"action_dropdown@{page_label}",
                        parent_id=parent_id,
                        depth=depth + 1,
                        discovery_method="action_button",
                        metadata={"button_count": count},
                    )
                    targets.append(target)
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
                    target = ExplorationTarget.create(
                        target_type=TargetType.MODAL,
                        locator=selector,
                        label=f"add_form_{label}@{page_label}",
                        parent_id=parent_id,
                        depth=depth + 1,
                        discovery_method="add_button",
                    )
                    targets.append(target)
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
                    target = ExplorationTarget.create(
                        target_type=TargetType.TAB_STATE,
                        locator=f"{icfg.tab_selector} >> nth={i}",
                        label=f"tab_{label}@{page_label}",
                        parent_id=parent_id,
                        depth=depth + 1,
                        discovery_method="tab_bar",
                        metadata={"tab_index": i, "tab_text": label},
                    )
                    targets.append(target)
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
                    target = ExplorationTarget.create(
                        target_type=TargetType.EXPANDED_ROW,
                        locator=selector,
                        label=f"expand_row@{page_label}",
                        parent_id=parent_id,
                        depth=depth + 1,
                        discovery_method="table_expand",
                        metadata={"expand_count": count},
                    )
                    targets.append(target)
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
        all_targets.extend(nav)
        coverage.nav_items_found = len(nav)

        actions = await self.extract_action_targets(page, parent_id, depth)
        all_targets.extend(actions)

        # Count raw action buttons and try to peek at dropdown items
        for selector in self.config.interaction.action_button_selectors:
            try:
                loc = page.locator(selector)
                count = await loc.count()
                if count > 0 and await loc.first.is_visible():
                    coverage.action_buttons_found = count
                    break
            except Exception:
                continue

        # Peek at dropdown items (without clicking) — count visible ones if any dropdown is open
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
