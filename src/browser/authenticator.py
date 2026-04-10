"""Authenticator handles public, login, and first-pass registration access flows."""

from __future__ import annotations

import asyncio

from playwright.async_api import TimeoutError as PwTimeout
from rich.console import Console

from src.config import AppConfig
from src.browser.controller import BrowserController

console = Console()


class Authenticator:
    """Handle the site's access flow before exploration begins."""

    def __init__(self, config: AppConfig, controller: BrowserController):
        self.config = config
        self.controller = controller
        self._manual_abort_requested = False

    @property
    def manual_abort_requested(self) -> bool:
        return self._manual_abort_requested

    async def login(self) -> bool:
        """Resolve and execute the configured access mode."""
        self._manual_abort_requested = False
        mode = self._resolve_mode()

        if mode == "public":
            console.print("[yellow]Access mode: public[/yellow]")
            return await self._enter_public_site()
        if mode == "manual":
            console.print("[yellow]Access mode: manual[/yellow]")
            return await self._manual_login()
        if mode == "register":
            console.print("[yellow]Access mode: register[/yellow]")
            return await self._register_account()
        if mode == "login":
            console.print("[yellow]Access mode: login[/yellow]")
            return await self._login_existing_account()

        console.print(f"[red]Unsupported access mode: {mode}[/red]")
        return False

    async def check_session(self) -> bool:
        """Check if the current run still appears authenticated."""
        mode = self._resolve_mode()
        if mode in {"public", "register"}:
            return True
        if await self._looks_like_verification_step():
            return False
        return not await self._looks_like_auth_surface()

    async def re_login(self) -> bool:
        """Re-authenticate if session expired."""
        mode = self._resolve_mode()
        if mode == "public":
            return True
        console.print("[yellow]Re-authenticating...[/yellow]")
        return await self.login()

    def _resolve_mode(self) -> str:
        cfg = self.config.login
        explicit = cfg.mode.strip().lower()
        if explicit in {"public", "login", "register", "manual"}:
            return explicit

        if cfg.username and cfg.password:
            return "login"
        if self.config.task.allow_registration_flows and (cfg.register_url or cfg.register_link_selector):
            return "register"
        return "public"

    async def _enter_public_site(self) -> bool:
        return await self._goto_with_retry(self.config.target.url)

    async def _login_existing_account(self) -> bool:
        cfg = self.config.login

        if not (cfg.username or self.config.task.profile_email):
            console.print("[red]Login mode requires a username/email or profile_email[/red]")
            return False
        if not await self._goto_with_retry(self.config.target.url):
            console.print("[red]Failed to reach login page after 3 attempts[/red]")
            return False

        return await self._advance_auth_flow("login")

    async def _manual_login(self) -> bool:
        if not self.config.task.human_assistance_allowed:
            console.print("[red]Manual login mode requires human assistance to be enabled[/red]")
            return False

        if not await self._goto_with_retry(self.config.target.url):
            console.print("[red]Failed to reach the target site before manual login[/red]")
            return False

        console.print(
            "[yellow]Please complete login manually in the visible browser, then return here and press Enter. "
            "Type 'abort' to stop.[/yellow]"
        )

        for attempt in range(5):
            try:
                response = await asyncio.to_thread(
                    console.input,
                    "[bold cyan]Press Enter after manual login is complete, or type 'abort': [/bold cyan]",
                )
            except EOFError:
                self._manual_abort_requested = True
                console.print("[red]Manual login aborted because no further terminal input was available[/red]")
                return False

            if response.strip().lower() == "abort":
                self._manual_abort_requested = True
                console.print("[red]Manual login aborted by user[/red]")
                return False

            await self._wait_after_submit()

            if await self._looks_like_verification_step():
                return await self._complete_manual_verification()

            success_indicator = self.config.login.success_indicator
            if success_indicator:
                try:
                    await self.controller.page.locator(success_indicator).first.wait_for(state="visible", timeout=3000)
                    return True
                except Exception:
                    pass

            if not await self._looks_like_auth_surface():
                return True

            console.print(
                f"[yellow]The current page still looks like an auth surface after attempt {attempt + 1}. "
                "Finish the login flow in the browser, then try again.[/yellow]"
            )

        console.print("[red]Manual login did not appear to reach a post-login product surface[/red]")
        return False

    async def _register_account(self) -> bool:
        cfg = self.config.login

        entry_url = cfg.register_url or self.config.target.url
        if not await self._goto_with_retry(entry_url):
            console.print("[red]Failed to reach registration page after 3 attempts[/red]")
            return False

        if cfg.register_link_selector:
            try:
                page = self.controller.page
                link = page.locator(cfg.register_link_selector).first
                await link.wait_for(state="visible", timeout=10000)
                await link.click()
                await self._wait_after_submit()
            except Exception as e:
                console.print(f"[yellow]Registration entry click skipped: {e}[/yellow]")

        return await self._advance_auth_flow("register")

    async def _goto_with_retry(self, url: str) -> bool:
        for attempt in range(3):
            if await self.controller.goto(url, timeout=60000):
                return True
            console.print(f"[yellow]Page load attempt {attempt + 1} failed, retrying...[/yellow]")
            await asyncio.sleep(2)
        return False

    async def _wait_after_submit(self) -> None:
        page = self.controller.page
        try:
            await page.wait_for_load_state("networkidle")
        except Exception:
            pass
        await asyncio.sleep(self.config.crawl.wait_for_spa / 1000)

    async def _advance_auth_flow(self, flow: str) -> bool:
        """Handle multi-step auth flows, including unified email-entry pages."""
        success_indicator = (
            self.config.login.registration_success_indicator or self.config.login.success_indicator
            if flow == "register"
            else self.config.login.success_indicator
        )

        seen_signatures: set[str] = set()
        for step_index in range(4):
            signature = await self._auth_step_signature(flow)
            if signature in seen_signatures:
                break
            seen_signatures.add(signature)

            submitted = await self._fill_and_submit_auth_step(flow)
            if not submitted:
                break

            await self._wait_after_submit()

            if await self._verify_success(success_indicator=success_indicator):
                return True

            if await self._looks_like_verification_step():
                return await self._complete_manual_verification()

            console.print(
                f"[cyan]Auth step {step_index + 1} completed; checking whether another auth step is required...[/cyan]"
            )

        if await self._verify_success(success_indicator=success_indicator):
            return True

        if await self._looks_like_verification_step():
            return await self._complete_manual_verification()

        console.print(f"[red]{flow.capitalize()} flow did not reach a verified product entry state[/red]")
        return False

    async def _fill_and_submit_auth_step(self, flow: str) -> bool:
        cfg = self.config.login
        task = self.config.task
        auth_scope = await self._locate_auth_scope()

        if flow == "register":
            email_value = task.profile_email
            password_value = task.profile_password
            await self._fill_optional(cfg.registration_name_selector, task.profile_name, scope=auth_scope)
            await self._fill_optional(cfg.registration_company_selector, task.profile_company, scope=auth_scope)
            await self._fill_optional(cfg.registration_email_selector, email_value, scope=auth_scope)
            await self._fill_optional(cfg.username_selector, email_value, scope=auth_scope)
            await self._fill_optional(cfg.registration_password_selector, password_value, scope=auth_scope)
            await self._fill_optional(cfg.registration_confirm_password_selector, password_value, scope=auth_scope)
            submit_selector = cfg.registration_submit_selector or cfg.submit_selector
        else:
            email_value = cfg.username or task.profile_email
            password_value = cfg.password or task.profile_password
            await self._fill_optional(cfg.username_selector, email_value, scope=auth_scope)
            await self._fill_optional(cfg.registration_email_selector, email_value, scope=auth_scope)
            await self._fill_optional(cfg.password_selector, password_value, scope=auth_scope)
            submit_selector = cfg.submit_selector

        if not await self._has_visible_auth_fields(flow, scope=auth_scope):
            return False

        if await self._click_first_visible(submit_selector, scope=auth_scope):
            return True

        return await self._submit_with_enter(flow, auth_scope)

    async def _has_visible_auth_fields(self, flow: str, scope=None) -> bool:
        cfg = self.config.login
        selectors = [cfg.username_selector, cfg.registration_email_selector]
        if flow == "register":
            selectors.extend([
                cfg.registration_name_selector,
                cfg.registration_password_selector,
                cfg.registration_confirm_password_selector,
                cfg.registration_company_selector,
            ])
        else:
            selectors.append(cfg.password_selector)

        for selector in selectors:
            if await self._has_visible_match(selector, scope=scope):
                return True
        return False

    async def _auth_step_signature(self, flow: str) -> str:
        cfg = self.config.login
        markers: list[str] = [flow, self.controller.page.url]
        selector_map = {
            "email": [cfg.username_selector, cfg.registration_email_selector],
            "password": [cfg.password_selector, cfg.registration_password_selector],
            "confirm": [cfg.registration_confirm_password_selector],
            "name": [cfg.registration_name_selector],
            "company": [cfg.registration_company_selector],
            "verification": [cfg.verification_code_selector],
        }
        for key, selectors in selector_map.items():
            visible = any([await self._has_visible_match(selector) for selector in selectors if selector])
            if visible:
                markers.append(key)
        return "|".join(markers)

    async def _verify_success(self, success_indicator: str) -> bool:
        page = self.controller.page
        if success_indicator:
            try:
                await page.locator(success_indicator).first.wait_for(state="visible", timeout=5000)
                return True
            except PwTimeout:
                console.print("[yellow]Success indicator not found; falling back to URL/state checks[/yellow]")

        if await self._looks_like_verification_step():
            console.print("[red]Verification is still required[/red]")
            return False

        if not await self._looks_like_auth_surface():
            return True

        console.print("[red]Still on an auth page after submit[/red]")
        return False

    async def _fill_first_visible(self, selector: str, value: str, scope=None) -> bool:
        if not selector or not value:
            return False

        root = scope or self.controller.page
        locator = root.locator(selector)
        count = await locator.count()
        for index in range(min(count, 5)):
            try:
                item = locator.nth(index)
                if not await item.is_visible():
                    continue
                try:
                    current_value = (await item.input_value() or "").strip()
                except Exception:
                    current_value = ""
                if current_value == value:
                    return True
                await item.fill(value)
                return True
            except Exception:
                continue
        return False

    async def _click_first_visible(self, selector: str, scope=None) -> bool:
        if not selector:
            return False

        root = scope or self.controller.page
        locator = root.locator(selector)
        count = await locator.count()
        for index in range(min(count, 8)):
            try:
                item = locator.nth(index)
                if not await item.is_visible():
                    continue
                await item.click()
                return True
            except Exception:
                continue
        return False

    async def _fill_optional(self, selector: str, value: str, scope=None) -> None:
        if not selector or not value:
            return
        await self._fill_first_visible(selector, value, scope=scope)

    async def _looks_like_auth_surface(self) -> bool:
        if await self._has_visible_match(self.config.login.verification_code_selector):
            return True

        auth_input_selectors = [
            self.config.login.username_selector,
            self.config.login.registration_email_selector,
            self.config.login.password_selector,
            self.config.login.registration_password_selector,
        ]
        if any([await self._has_visible_match(selector) for selector in auth_input_selectors if selector]):
            return True
        return False

    async def _has_visible_match(self, selector: str, scope=None) -> bool:
        if not selector:
            return False
        root = scope or self.controller.page
        locator = root.locator(selector)
        try:
            count = await locator.count()
            for index in range(min(count, 8)):
                if await locator.nth(index).is_visible():
                    return True
        except Exception:
            return False
        return False

    async def _locate_auth_scope(self):
        page = self.controller.page
        container_selectors = [
            "form",
            "[role='dialog']",
        ]
        auth_inputs = [
            self.config.login.username_selector,
            self.config.login.registration_email_selector,
            self.config.login.password_selector,
            self.config.login.registration_password_selector,
            self.config.login.verification_code_selector,
        ]

        for container_selector in container_selectors:
            locator = page.locator(container_selector)
            try:
                count = await locator.count()
            except Exception:
                continue
            for index in range(min(count, 10)):
                candidate = locator.nth(index)
                try:
                    if not await candidate.is_visible():
                        continue
                    for selector in auth_inputs:
                        if not selector:
                            continue
                        if await self._has_visible_match(selector, scope=candidate):
                            return candidate
                except Exception:
                    continue
        return None

    async def _submit_with_enter(self, flow: str, scope=None) -> bool:
        selectors = []
        if flow == "register":
            selectors.extend([
                self.config.login.registration_confirm_password_selector,
                self.config.login.registration_password_selector,
                self.config.login.registration_email_selector,
                self.config.login.username_selector,
            ])
        else:
            selectors.extend([
                self.config.login.password_selector,
                self.config.login.registration_email_selector,
                self.config.login.username_selector,
            ])

        root = scope or self.controller.page
        for selector in selectors:
            if not selector:
                continue
            locator = root.locator(selector)
            try:
                count = await locator.count()
            except Exception:
                continue
            for index in range(min(count, 5)):
                try:
                    item = locator.nth(index)
                    if not await item.is_visible():
                        continue
                    await item.press("Enter")
                    return True
                except Exception:
                    continue

        try:
            await self.controller.page.keyboard.press("Enter")
            return True
        except Exception:
            return False

    async def _looks_like_verification_step(self) -> bool:
        cfg = self.config.login
        page = self.controller.page

        code_input = page.locator(cfg.verification_code_selector)
        visible_inputs = 0
        try:
            count = await code_input.count()
            for index in range(min(count, 8)):
                if await code_input.nth(index).is_visible():
                    visible_inputs += 1
        except Exception:
            visible_inputs = 0

        return bool(visible_inputs)

    async def _complete_manual_verification(self) -> bool:
        if not self.config.task.human_assistance_allowed:
            console.print("[red]Verification is required but human assistance is disabled[/red]")
            return False

        console.print(
            "[yellow]Verification step detected. Keep the visible browser open, "
            "get the code or magic link from email, or complete the verification manually, then continue here.[/yellow]"
        )

        for attempt in range(5):
            try:
                response = await asyncio.to_thread(
                    console.input,
                    "[bold cyan]Enter verification code, paste the verification URL, or press Enter after you complete the step manually in the browser. Type 'abort' to stop: [/bold cyan]",
                )
            except EOFError:
                self._manual_abort_requested = True
                console.print("[red]Verification aborted because no further terminal input was available[/red]")
                return False
            code = response.strip()
            if code.lower() == "abort":
                self._manual_abort_requested = True
                console.print("[red]Verification aborted by user[/red]")
                return False

            if code.lower().startswith(("http://", "https://")):
                console.print("[cyan]Opening the verification URL in the visible browser session...[/cyan]")
                if not await self._goto_with_retry(code):
                    console.print("[yellow]Failed to open the pasted verification URL[/yellow]")
                    continue
            elif code:
                filled = await self._fill_verification_code(code)
                if not filled:
                    console.print(
                        "[yellow]Could not auto-fill a visible verification input. "
                        "You can still paste the code or open the verification URL manually in the browser, then press Enter here.[/yellow]"
                    )
                else:
                    await self._submit_verification_if_possible()
            else:
                console.print("[cyan]Checking whether verification already completed...[/cyan]")

            await self._wait_after_submit()

            if await self._verify_success(
                success_indicator=self.config.login.registration_success_indicator or self.config.login.success_indicator,
            ):
                return True

            console.print(
                f"[yellow]Verification still appears incomplete after attempt {attempt + 1}. "
                "Try another code or finish the step manually in the visible browser.[/yellow]"
            )

        console.print("[red]Verification did not complete after multiple attempts[/red]")
        return False

    async def _fill_verification_code(self, code: str) -> bool:
        locator = self.controller.page.locator(self.config.login.verification_code_selector)
        visible_inputs = []
        try:
            count = await locator.count()
            for index in range(min(count, 8)):
                item = locator.nth(index)
                if await item.is_visible():
                    visible_inputs.append(item)
        except Exception:
            return False

        if not visible_inputs:
            return False

        if len(visible_inputs) == 1:
            try:
                await visible_inputs[0].fill(code)
                return True
            except Exception:
                return False

        digits = list(code)
        if len(digits) < len(visible_inputs):
            return False

        for item, value in zip(visible_inputs, digits):
            try:
                await item.fill(value)
            except Exception:
                return False
        return True

    async def _submit_verification_if_possible(self) -> None:
        selectors = [
            self.config.login.verification_submit_selector,
            self.config.login.registration_submit_selector,
            self.config.login.submit_selector,
        ]
        for selector in selectors:
            if not selector:
                continue
            try:
                locator = self.controller.page.locator(selector)
                count = await locator.count()
                for index in range(min(count, 5)):
                    item = locator.nth(index)
                    if not await item.is_visible():
                        continue
                    await item.click()
                    return
            except Exception:
                continue

        try:
            await self.controller.page.keyboard.press("Enter")
        except Exception:
            pass
