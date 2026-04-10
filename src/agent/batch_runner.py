"""Batch orchestration for concurrent multi-site UX runs."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from rich.console import Console

from src.agent.engine import ExplorationEngine
from src.config import AppConfig, apply_run_profile, load_batch_config, load_config, load_config_for_url

console = Console()


class BatchRunner:
    """Run multiple site configs concurrently and aggregate UX report outputs."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path(__file__).parent.parent.parent

    async def run(
        self,
        batch_config_path: str,
        profile: str | None = None,
        max_states: int | None = None,
        max_depth: int | None = None,
        headless: bool = False,
        clear: bool = False,
    ) -> dict[str, Any]:
        batch_config, batch_dir = load_batch_config(batch_config_path)
        batch_name = self._slug(batch_config.name or Path(batch_config_path).stem)
        batch_root_rel = Path(batch_config.output_root) / batch_name
        batch_root = self.project_root / batch_root_rel

        if clear and batch_root.exists():
            shutil.rmtree(batch_root)
        batch_root.mkdir(parents=True, exist_ok=True)

        console.print(
            f"[cyan]Running batch `{batch_name}` with {len(batch_config.sites)} site(s)[/cyan]"
        )

        max_concurrent_sites = max(1, int(batch_config.max_concurrent_sites))
        site_semaphore = asyncio.Semaphore(max_concurrent_sites)
        tasks = [
            self._run_site_with_limit(
                site=site.model_dump(),
                batch_dir=batch_dir,
                batch_root_rel=batch_root_rel,
                profile=profile,
                max_states=max_states,
                max_depth=max_depth,
                headless=headless,
                site_semaphore=site_semaphore,
            )
            for site in batch_config.sites
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        site_names = [site.name for site in batch_config.sites]
        return self._finalize_batch_results(
            batch_name=batch_name,
            batch_root=batch_root,
            site_count=len(batch_config.sites),
            site_names=site_names,
            results=results,
        )

    async def run_urls(
        self,
        urls: list[str],
        base_config_path: str | None = None,
        profile: str | None = None,
        max_states: int | None = None,
        max_depth: int | None = None,
        headless: bool = False,
        clear: bool = False,
        max_concurrent_sites: int = 3,
    ) -> dict[str, Any]:
        """Run one to three ad-hoc target URLs using a shared base config."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_name = f"adhoc_{timestamp}"
        batch_root_rel = Path("output/batch") / batch_name
        batch_root = self.project_root / batch_root_rel

        if clear and batch_root.exists():
            shutil.rmtree(batch_root)
        batch_root.mkdir(parents=True, exist_ok=True)

        console.print(
            f"[cyan]Running ad-hoc batch `{batch_name}` with {len(urls)} site(s)[/cyan]"
        )

        site_semaphore = asyncio.Semaphore(max(1, int(max_concurrent_sites)))
        tasks = [
            self._run_url_site_with_limit(
                target_url=url,
                base_config_path=base_config_path,
                batch_root_rel=batch_root_rel,
                profile=profile,
                max_states=max_states,
                max_depth=max_depth,
                headless=headless,
                site_semaphore=site_semaphore,
            )
            for url in urls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        site_names = [self._display_name_from_url(url) for url in urls]
        return self._finalize_batch_results(
            batch_name=batch_name,
            batch_root=batch_root,
            site_count=len(urls),
            site_names=site_names,
            results=results,
        )

    async def _run_site_with_limit(
        self,
        site: dict[str, Any],
        batch_dir: Path,
        batch_root_rel: Path,
        profile: str | None,
        max_states: int | None,
        max_depth: int | None,
        headless: bool,
        site_semaphore: asyncio.Semaphore,
    ) -> dict[str, Any]:
        async with site_semaphore:
            return await self._run_site(
                site=site,
                batch_dir=batch_dir,
                batch_root_rel=batch_root_rel,
                profile=profile,
                max_states=max_states,
                max_depth=max_depth,
                headless=headless,
            )

    async def _run_url_site_with_limit(
        self,
        target_url: str,
        base_config_path: str | None,
        batch_root_rel: Path,
        profile: str | None,
        max_states: int | None,
        max_depth: int | None,
        headless: bool,
        site_semaphore: asyncio.Semaphore,
    ) -> dict[str, Any]:
        async with site_semaphore:
            return await self._run_url_site(
                target_url=target_url,
                base_config_path=base_config_path,
                batch_root_rel=batch_root_rel,
                profile=profile,
                max_states=max_states,
                max_depth=max_depth,
                headless=headless,
            )

    async def _run_site(
        self,
        site: dict[str, Any],
        batch_dir: Path,
        batch_root_rel: Path,
        profile: str | None,
        max_states: int | None,
        max_depth: int | None,
        headless: bool,
    ) -> dict[str, Any]:
        site_name = str(site["name"])
        site_slug = self._slug(site_name)
        config_path = Path(site["config"])
        if not config_path.is_absolute():
            config_path = (batch_dir / config_path).resolve()

        config = load_config(config_path)
        return await self._run_loaded_config(
            config=config,
            site_name=site_name,
            site_slug=site_slug,
            batch_root_rel=batch_root_rel,
            profile=profile,
            max_states=max_states if max_states is not None else site.get("max_states"),
            max_depth=max_depth if max_depth is not None else site.get("max_depth"),
            headless=headless,
        )

    async def _run_url_site(
        self,
        target_url: str,
        base_config_path: str | None,
        batch_root_rel: Path,
        profile: str | None,
        max_states: int | None,
        max_depth: int | None,
        headless: bool,
    ) -> dict[str, Any]:
        site_name = self._display_name_from_url(target_url)
        site_slug = self._slug(self._site_key_from_url(target_url))
        config = load_config_for_url(target_url, base_config_path)
        return await self._run_loaded_config(
            config=config,
            site_name=site_name,
            site_slug=site_slug,
            batch_root_rel=batch_root_rel,
            profile=profile,
            max_states=max_states,
            max_depth=max_depth,
            headless=headless,
        )

    async def _run_loaded_config(
        self,
        config: AppConfig,
        site_name: str,
        site_slug: str,
        batch_root_rel: Path,
        profile: str | None,
        max_states: int | None,
        max_depth: int | None,
        headless: bool,
    ) -> dict[str, Any]:
        apply_run_profile(config, profile)
        self._apply_output_override(config, batch_root_rel, site_slug)
        self._apply_overrides(
            config,
            max_states=max_states,
            max_depth=max_depth,
            headless=headless,
        )

        engine = ExplorationEngine(config)
        await engine.run()

        artifacts_root = self.project_root / config.output.artifacts_dir
        reports_root = self.project_root / config.output.reports_dir
        report_path = reports_root / config.synthesis.ux_report_filename_md

        if not report_path.exists():
            raise RuntimeError(f"{site_name}: missing {config.synthesis.ux_report_filename_md}")

        return {
            "name": site_name,
            "slug": site_slug,
            "ux_report_path": str(report_path),
            "artifacts_path": str(artifacts_root),
        }

    def _finalize_batch_results(
        self,
        batch_name: str,
        batch_root: Path,
        site_count: int,
        site_names: list[str],
        results: list[dict[str, Any] | Exception],
    ) -> dict[str, Any]:
        successes: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        for site_name, result in zip(site_names, results):
            if isinstance(result, Exception):
                failures.append({"name": site_name, "error": str(result)})
                continue
            successes.append(result)

        summary = {
            "batch_name": batch_name,
            "generated_at": datetime.now().isoformat(),
            "site_count": site_count,
            "successful_sites": len(successes),
            "failed_sites": failures,
            "sites": [
                {
                    "name": item["name"],
                    "slug": item["slug"],
                    "ux_report_path": item["ux_report_path"],
                    "artifacts_path": item["artifacts_path"],
                }
                for item in successes
            ],
        }
        (batch_root / "batch_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return summary

    def _apply_output_override(self, config: AppConfig, batch_root_rel: Path, site_slug: str) -> None:
        site_base = batch_root_rel / "sites" / site_slug
        config.output.screenshots_dir = str(site_base / "screenshots").replace("\\", "/")
        config.output.dom_snapshots_dir = str(site_base / "dom_snapshots").replace("\\", "/")
        config.output.reports_dir = str(site_base / "reports").replace("\\", "/")
        config.output.artifacts_dir = str(site_base / "artifacts").replace("\\", "/")

    def _apply_overrides(
        self,
        config: AppConfig,
        max_states: int | None,
        max_depth: int | None,
        headless: bool,
    ) -> None:
        if max_states is not None:
            config.budget.max_states = int(max_states)
        if max_depth is not None:
            config.budget.max_depth = int(max_depth)
        if headless:
            config.browser.headless = True

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_").lower()
        return slug or "site"

    def _display_name_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        host = parsed.netloc.lower() or url
        path = parsed.path.strip("/")
        return f"{host}/{path}" if path else host

    def _site_key_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        host = parsed.netloc.lower() or "site"
        path = parsed.path.strip("/").replace("/", "_")
        return f"{host}_{path}" if path else host
