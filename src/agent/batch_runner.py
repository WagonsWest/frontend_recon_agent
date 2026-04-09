"""Batch orchestration for concurrent multi-site runs."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from src.agent.engine import ExplorationEngine
from src.analysis.comparison_report import ComparisonReportGenerator
from src.config import AppConfig, apply_run_profile, load_batch_config, load_config

console = Console()


class BatchRunner:
    """Run multiple site configs concurrently and generate a comparison report."""

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

        tasks = [
            self._run_site(
                site=site.model_dump(),
                batch_dir=batch_dir,
                batch_root_rel=batch_root_rel,
                profile=profile,
                max_states=max_states,
                max_depth=max_depth,
                headless=headless,
            )
            for site in batch_config.sites
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        for site, result in zip(batch_config.sites, results):
            if isinstance(result, Exception):
                failures.append({"name": site.name, "error": str(result)})
                continue
            successes.append(result)

        reports_dir = batch_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        comparison = self._build_comparison_payload(successes, reports_dir)
        comparison_path = reports_dir / "comparison_report.md"
        comparison_path.write_text(
            ComparisonReportGenerator().generate_markdown(comparison),
            encoding="utf-8",
        )
        (reports_dir / "comparison_report.json").write_text(
            json.dumps(comparison, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        summary = {
            "batch_name": batch_name,
            "generated_at": datetime.now().isoformat(),
            "site_count": len(batch_config.sites),
            "successful_sites": len(successes),
            "failed_sites": failures,
            "comparison_report": str(comparison_path),
        }
        (batch_root / "batch_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return summary

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
        apply_run_profile(config, profile)
        self._apply_output_override(config, batch_root_rel, site_slug)
        self._apply_overrides(
            config,
            max_states=max_states if max_states is not None else site.get("max_states"),
            max_depth=max_depth if max_depth is not None else site.get("max_depth"),
            headless=headless,
        )

        engine = ExplorationEngine(config)
        await engine.run()

        artifacts_root = self.project_root / config.output.artifacts_dir
        reports_root = self.project_root / config.output.reports_dir
        analysis_path = artifacts_root / "competitive_analysis.json"
        report_path = reports_root / config.synthesis.readable_report_filename_md

        if not analysis_path.exists():
            raise RuntimeError(f"{site_name}: missing competitive_analysis.json")

        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        return {
            "name": site_name,
            "slug": site_slug,
            "analysis": analysis,
            "readable_report_path": str(report_path),
        }

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
        if headless or config.browser.headless:
            console.print(
                "[yellow]Visible browser mode is enforced for interactive auth and verification; ignoring headless setting.[/yellow]"
            )
        config.browser.headless = False

    def _build_comparison_payload(
        self,
        successes: list[dict[str, Any]],
        reports_dir: Path,
    ) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for item in successes:
            analysis = item["analysis"]
            summary = analysis.get("competitive_summary", {})
            readable_report_path = Path(item["readable_report_path"])
            payload.append({
                "name": item["name"],
                "target": analysis.get("target", "unknown"),
                "product_category_guess": summary.get("product_category_guess", "unknown"),
                "summary": {
                    "application_surface_score": float(summary.get("application_surface_score", 0)),
                    "data_density_score": float(summary.get("data_density_score", 0)),
                    "workflow_complexity_score": float(summary.get("workflow_complexity_score", 0)),
                },
                "page_type_distribution": analysis.get("page_type_distribution", {}),
                "modules": [module.get("name", "unknown") for module in analysis.get("feature_modules", [])],
                "strengths": summary.get("observed_strengths", []),
                "gaps": summary.get("observed_gaps", []),
                "readable_report_path": self._relpath(readable_report_path, reports_dir),
            })
        return payload

    def _relpath(self, path: Path, start: Path) -> str:
        return os.path.relpath(path, start).replace("\\", "/")

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_").lower()
        return slug or "site"
