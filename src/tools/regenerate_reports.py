"""Regenerate competitive-analysis reports from existing artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import click

from src.agent.state import AgentState, ExplorationTarget, StateSnapshot, TargetType, VisitStatus
from src.analysis.competitive_report import CompetitiveReportGenerator
from src.analysis.readable_report import ReadableCompetitiveReportGenerator
from src.config import load_config


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows[str(row.get("state_id", ""))] = row
    return rows


def _report_screenshot_path(path: Path) -> str:
    if not path.exists():
        return ""
    candidate = path.with_name(f"{path.stem}_report{path.suffix}")
    return str(candidate) if candidate.exists() else ""


def _rebuild_state(artifacts_root: Path) -> AgentState:
    inventory = _load_json(artifacts_root / "inventory.json")
    sitemap = _load_json(artifacts_root / "sitemap.json")
    max_depth = max((int(node.get("depth", 0)) for node in sitemap.get("nodes", [])), default=0)
    state = AgentState(budget=max(len(inventory), 1), max_depth=max_depth)
    state.budget_remaining = 0

    for node in sitemap.get("nodes", []):
        raw_type = str(node.get("type", "route"))
        try:
            target_type = TargetType(raw_type)
        except ValueError:
            target_type = TargetType.ROUTE

        target = ExplorationTarget(
            id=str(node.get("id", "")),
            target_type=target_type,
            locator="",
            label=str(node.get("label", "")),
            parent_id=str(node.get("parent", "")) or None,
            depth=int(node.get("depth", 0)),
            discovery_method=str(node.get("discovery_method", "")),
        )
        state.targets[target.id] = target
        if node.get("visited"):
            state.visited.add(target.id)
        if node.get("skipped"):
            state.skipped.add(target.id)

    for item in inventory:
        screenshot_path = Path(str(item.get("screenshot", "")))
        snapshot = StateSnapshot(
            id=str(item.get("id", "")),
            target_id=str(item.get("target_id", "")),
            url=str(item.get("url", "")),
            title=str(item.get("title", "")),
            timestamp=str(item.get("timestamp", "")),
            screenshot_path=str(screenshot_path),
            html_path=str(item.get("html", "")),
            visit_status=VisitStatus(str(item.get("visit_status", "success"))),
            novelty_score=float(item.get("novelty_score", 0.0)),
            depth=int(item.get("depth", 0)),
            retry_count=int(item.get("retries", 0)),
            error=item.get("error"),
            metadata={
                "capture_label": str(item.get("label", "")),
                "capture_context": str(item.get("target_type", "")),
                "report_screenshot_path": _report_screenshot_path(screenshot_path),
            },
        )
        state.states[snapshot.id] = snapshot

    return state


def _load_per_state_dir(path: Path, suffix: str = ".json") -> dict[str, dict]:
    items: dict[str, dict] = {}
    if not path.exists():
        return items
    for file in path.glob(f"*{suffix}"):
        key = file.stem.replace("_insight", "").replace("_vision", "")
        items[key] = json.loads(file.read_text(encoding="utf-8"))
    return items


@click.command()
@click.option("--config", "config_path", default=None, help="Path to config YAML file")
@click.option("--artifacts-dir", default=None, help="Override artifacts directory")
@click.option("--reports-dir", default=None, help="Override reports directory")
def main(config_path: str | None, artifacts_dir: str | None, reports_dir: str | None) -> None:
    """Regenerate competitive-analysis reports from existing output artifacts."""
    config = load_config(config_path)
    project_root = Path(__file__).parent.parent.parent
    artifacts_root = project_root / (artifacts_dir or config.output.artifacts_dir)
    reports_root = project_root / (reports_dir or config.output.reports_dir)
    reports_root.mkdir(parents=True, exist_ok=True)

    state = _rebuild_state(artifacts_root)
    analysis_results = _load_per_state_dir(artifacts_root / "analysis")
    page_insights = _load_per_state_dir(artifacts_root / config.vision.page_insights_dir)
    extraction_results = _load_jsonl(artifacts_root / "dataset.jsonl")

    generator = CompetitiveReportGenerator()
    readable_generator = ReadableCompetitiveReportGenerator()
    competitive = generator.generate(
        state,
        analysis_results=analysis_results,
        page_insights=page_insights,
        extraction_results=extraction_results,
    )

    (artifacts_root / "competitive_analysis.json").write_text(
        json.dumps(competitive.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (reports_root / config.synthesis.structured_report_filename_md).write_text(
        generator.generate_markdown(competitive),
        encoding="utf-8",
    )
    (reports_root / config.synthesis.artifact_filename_md).write_text(
        generator.generate_markdown(competitive),
        encoding="utf-8",
    )
    (reports_root / config.synthesis.readable_report_filename_md).write_text(
        readable_generator.generate(
            state,
            competitive,
            page_insights,
            extraction_results,
            reports_root,
        ),
        encoding="utf-8",
    )

    click.echo(f"Regenerated reports in {reports_root}")


if __name__ == "__main__":
    main()
