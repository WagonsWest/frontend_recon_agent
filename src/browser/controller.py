"""Browser controller — Playwright lifecycle and single-action capture interface."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Locator
from playwright.async_api import TimeoutError as PwTimeout

from src.config import AppConfig


class BrowserController:
    """Controls browser: launch, navigate, click, capture. No crawl logic."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._project_root = Path(__file__).parent.parent.parent
        self._capture_counter = 0

    @property
    def page(self) -> Page:
        assert self._page is not None, "Browser not started"
        return self._page

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        headless = bool(self.config.browser.headless)
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            slow_mo=self.config.browser.slow_mo,
        )
        self._context = await self._browser.new_context(
            viewport={
                "width": self.config.browser.viewport_width,
                "height": self.config.browser.viewport_height,
            },
        )
        self._page = await self._context.new_page()

        # Handle new tabs: close them and stay on the main page
        self._context.on("page", self._handle_new_page)

    def _handle_new_page(self, new_page) -> None:
        """Close any new tabs/popups that open, keeping focus on the main page."""
        async def _close():
            try:
                await new_page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            try:
                await new_page.close()
            except Exception:
                pass
        asyncio.ensure_future(_close())

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def goto(self, url: str, timeout: int = 30000) -> bool:
        """Navigate to URL. Returns True on success."""
        try:
            wait_until = self.config.run.navigation_wait_until or "networkidle"
            await self.page.goto(url, wait_until=wait_until, timeout=timeout)
            await asyncio.sleep(self.config.crawl.wait_for_spa / 1000)
            return True
        except PwTimeout:
            # Page may have partially loaded — that's often OK for SPAs
            await asyncio.sleep(self.config.crawl.wait_for_spa / 1000)
            return True
        except Exception:
            return False

    async def click(self, selector: str, timeout: int = 5000) -> bool:
        """Click an element. Returns True on success."""
        try:
            loc = self.page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout)
            await loc.click()
            await asyncio.sleep(self.config.crawl.wait_after_navigation / 1000)
            return True
        except Exception:
            return False

    async def click_locator(self, locator: Locator, wait: float | None = None) -> bool:
        """Click a Playwright Locator directly. Returns True on success."""
        try:
            await locator.click()
            await asyncio.sleep(wait if wait is not None else self.config.crawl.wait_after_navigation / 1000)
            return True
        except Exception:
            return False

    async def go_back(self) -> bool:
        """Browser back. Returns True on success."""
        try:
            await self.page.go_back()
            await asyncio.sleep(self.config.crawl.wait_after_navigation / 1000)
            return True
        except Exception:
            return False

    async def press_escape(self) -> None:
        """Press Escape to dismiss overlays."""
        try:
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
        except Exception:
            pass

    async def close_overlays(self) -> None:
        """Close any open modals/drawers using configured selectors."""
        await self.press_escape()
        for selector in self.config.interaction.modal_close_selectors:
            try:
                btn = self.page.locator(selector).first
                if await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(0.5)
                    return
            except Exception:
                continue
        await self.press_escape()

    async def get_url(self) -> str:
        return self.page.url

    async def get_title(self) -> str:
        return await self.page.title()

    async def get_html(self) -> str:
        return await self.page.content()

    async def capture_screenshot(self, label: str, context: str = "nav", full_page: bool = True) -> str:
        """Take full-page screenshot. Returns path."""
        self._capture_counter += 1
        safe_label = re.sub(r'[^\w\-\u4e00-\u9fff]', '_', label)[:40]
        name = f"{self._capture_counter:03d}_{safe_label}_{context}.png"
        path = self._project_root / self.config.output.screenshots_dir / name
        try:
            await self.page.screenshot(path=str(path), full_page=full_page)
        except Exception:
            if not full_page:
                raise
            await self.page.screenshot(path=str(path), full_page=False)
        return str(path)

    async def capture_viewport_screenshot(self, label: str, context: str = "vision") -> str:
        """Take a viewport screenshot. Returns path."""
        self._capture_counter += 1
        safe_label = re.sub(r'[^\w\-\u4e00-\u9fff]', '_', label)[:40]
        name = f"{self._capture_counter:03d}_{safe_label}_{context}.png"
        path = self._project_root / self.config.output.screenshots_dir / name
        await self.page.screenshot(path=str(path), full_page=False)
        return str(path)

    async def save_html(self, label: str, context: str = "nav") -> str:
        """Save current DOM to file. Returns path."""
        html = await self.get_html()
        safe_label = re.sub(r'[^\w\-\u4e00-\u9fff]', '_', label)[:40]
        name = f"{self._capture_counter:03d}_{safe_label}_{context}.html"
        path = self._project_root / self.config.output.dom_snapshots_dir / name
        try:
            path.write_text(html, encoding="utf-8")
        except OSError:
            pass
        return str(path)

    async def evaluate(self, script: str, default: Any = None) -> Any:
        """Run JS in page context with error handling."""
        try:
            return await self.page.evaluate(script)
        except Exception:
            return default

    async def get_computed_styles(self) -> dict[str, dict[str, str]]:
        """Extract computed styles for key layout elements."""
        selectors = self.config.browser.style_selectors
        try:
            return await self.page.evaluate("""
                (selectors) => {
                    const result = {};
                    for (const sel of selectors) {
                        try {
                            const el = document.querySelector(sel);
                            if (!el) continue;
                            const cs = window.getComputedStyle(el);
                            result[sel] = {
                                color: cs.color, backgroundColor: cs.backgroundColor,
                                fontFamily: cs.fontFamily, fontSize: cs.fontSize,
                                fontWeight: cs.fontWeight, padding: cs.padding,
                                margin: cs.margin, display: cs.display,
                                position: cs.position, width: cs.width,
                                height: cs.height, borderRadius: cs.borderRadius,
                                boxShadow: cs.boxShadow,
                            };
                        } catch (e) {}
                    }
                    return result;
                }
            """, selectors)
        except Exception:
            return {}

    async def find_first_visible(self, selectors: list[str]) -> tuple[Locator | None, int]:
        """Find first visible element matching any selector. Returns (locator, count)."""
        for selector in selectors:
            try:
                loc = self.page.locator(selector)
                count = await loc.count()
                if count > 0 and await loc.first.is_visible():
                    return loc, count
            except Exception:
                continue
        return None, 0

    async def is_modal_open(self) -> bool:
        """Check if any modal/dialog/drawer is currently visible."""
        for selector in self.config.interaction.modal_selectors:
            try:
                if await self.page.locator(selector).first.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def detect_captcha_or_antibot(self) -> dict[str, Any]:
        """Detect likely captcha or anti-bot challenges on the current page."""
        selectors = [
            "iframe[src*='recaptcha']",
            ".g-recaptcha",
            "#captcha",
            "[id*='captcha']",
            "[class*='captcha']",
            "input[name*='captcha']",
            "input[id*='captcha']",
            "iframe[title*='challenge']",
            "#cf-challenge-running",
            "[data-testid*='captcha']",
        ]

        visible_selectors: list[str] = []
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if await locator.is_visible():
                    visible_selectors.append(selector)
            except Exception:
                continue

        text_matches = await self.evaluate("""
            () => {
                const text = (document.body?.innerText || '').toLowerCase();
                const phrases = [
                    'captcha',
                    'verify you are human',
                    'verification required',
                    'unusual traffic',
                    'press and hold',
                    'are you human',
                    'security check'
                ];
                return phrases.filter((phrase) => text.includes(phrase));
            }
        """, default=[])

        detected = bool(visible_selectors or text_matches)
        return {
            "detected": detected,
            "selector_matches": visible_selectors,
            "text_matches": text_matches or [],
        }
