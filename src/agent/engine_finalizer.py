"""Finalization runtime extracted from the main engine."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel

from src.agent.state import AgentPhase
from src.analysis.runtime_artifacts import (
    build_operation_trace,
    build_site_hierarchy,
    render_operation_trace_markdown,
    render_site_hierarchy_markdown,
)
from src.analysis.ux_report import UserExperienceReportGenerator
from src.artifacts.inventory import InventoryGenerator
from src.artifacts.report import ReportGenerator
from src.artifacts.sitemap import SitemapGenerator

if TYPE_CHECKING:
    from src.agent.engine import ExplorationEngine

console = Console()


class FinalizationRuntime:
    """Owns artifact generation and final reporting."""

    def __init__(self, engine: "ExplorationEngine"):
        self.engine = engine

    async def phase_finalize(self) -> None:
        self.engine.state.phase = AgentPhase.FINALIZE
        end_time = datetime.now().isoformat()
        run_log_entries = self.engine.logger.rows()

        console.print("\n[bold]Generating artifacts...[/bold]")

        with self.engine.logger.timed(AgentPhase.FINALIZE, "generate_inventory") as ctx:
            inventory = InventoryGenerator().generate(self.engine.state)
            path = self.engine.artifacts.save_json("inventory.json", inventory)
            ctx["reason"] = f"{len(inventory)} entries -> {path.name}"

        with self.engine.logger.timed(AgentPhase.FINALIZE, "generate_sitemap") as ctx:
            sitemap = SitemapGenerator().generate(self.engine.state)
            path = self.engine.artifacts.save_json("sitemap.json", sitemap)
            ctx["reason"] = f"{sitemap['stats']['total_nodes']} nodes -> {path.name}"

        with self.engine.logger.timed(AgentPhase.FINALIZE, "generate_coverage") as ctx:
            coverage_data = {tid: asdict(cov) for tid, cov in self.engine.state.coverage.items()}
            path = self.engine.artifacts.save_json("coverage.json", coverage_data)
            pages_with_gaps = sum(1 for c in self.engine.state.coverage.values() if c.has_unexplored)
            ctx["reason"] = f"{len(coverage_data)} pages, {pages_with_gaps} with gaps -> {path.name}"

        with self.engine.logger.timed(AgentPhase.FINALIZE, "generate_site_memory") as ctx:
            path = self.engine.artifacts.save_json("site_memory.json", self.engine._site_memory)
            ctx["reason"] = f"site memory -> {path.name}"

        with self.engine.logger.timed(AgentPhase.FINALIZE, "generate_operation_trace") as ctx:
            operation_trace = build_operation_trace(run_log_entries)
            json_path = self.engine.artifacts.save_json("operation_trace.json", operation_trace)
            md_path = self.engine.artifacts.save_text(
                "operation_trace.md",
                render_operation_trace_markdown(operation_trace),
            )
            ctx["reason"] = f"{operation_trace['stats']['total_steps']} steps -> {json_path.name}, {md_path.name}"

        with self.engine.logger.timed(AgentPhase.FINALIZE, "generate_site_hierarchy") as ctx:
            site_hierarchy = build_site_hierarchy(self.engine.state)
            json_path = self.engine.artifacts.save_json("site_hierarchy.json", site_hierarchy)
            md_path = self.engine.artifacts.save_text(
                "site_hierarchy.md",
                render_site_hierarchy_markdown(site_hierarchy),
            )
            ctx["reason"] = f"{site_hierarchy['stats']['visited_nodes']} visited nodes -> {json_path.name}, {md_path.name}"

        with self.engine.logger.timed(AgentPhase.FINALIZE, "generate_extraction_artifacts") as ctx:
            extraction_rows = list(self.engine._extraction_results.values())
            summary = self.build_extraction_summary(extraction_rows)
            failures = [
                row for row in extraction_rows
                if row.get("status") in {"failed", "empty"} or row.get("error")
            ]
            self.engine.artifacts.save_jsonl("dataset.jsonl", extraction_rows)
            self.engine.artifacts.save_json("dataset_summary.json", summary)
            self.engine.artifacts.save_json("extraction_failures.json", failures)
            ctx["reason"] = (
                f"{summary['total_results']} results, "
                f"{summary['successful_results']} successful"
            )

        with self.engine.logger.timed(AgentPhase.FINALIZE, "generate_report") as ctx:
            report = ReportGenerator().generate(
                self.engine.state,
                self.engine._start_time,
                end_time,
                self.engine._analysis_results,
                self.engine._page_insights,
                self.engine._extraction_results,
            )
            path = self.engine.artifacts.save_text("exploration_report.md", report)
            ctx["reason"] = f"report -> {path.name}"

        with self.engine.logger.timed(AgentPhase.FINALIZE, "generate_ux_report") as ctx:
            ux_markdown = UserExperienceReportGenerator().generate(
                self.engine.state,
                self.engine._page_insights,
                self.engine._extraction_results,
                self.engine.artifacts.reports_dir(),
                run_log_entries=run_log_entries,
                coverage_data=coverage_data,
                operation_trace=operation_trace,
                site_hierarchy=site_hierarchy,
            )
            path = self.engine.artifacts.save_text(
                self.engine.config.synthesis.ux_report_filename_md,
                ux_markdown,
            )
            ctx["reason"] = f"ux report -> {path.name}"

        if self.engine.config.run.enable_timing_summary:
            timing_path = self.engine.artifacts.save_json("run_timing_summary.json", self.engine.logger.summary())
            self.engine.logger.log(
                AgentPhase.FINALIZE,
                "generate_timing_summary",
                "",
                "success",
                f"timing summary -> {timing_path.name}",
            )
            observe_breakdown_path = self.engine.artifacts.save_json(
                "run_observe_breakdown.json",
                self.observe_breakdown_summary(),
            )
            self.engine.logger.log(
                AgentPhase.FINALIZE,
                "generate_observe_breakdown",
                "",
                "success",
                f"observe breakdown -> {observe_breakdown_path.name}",
            )

        stats = self.engine.state.get_stats()
        console.print(
            Panel.fit(
                f"[bold green]Exploration Complete[/bold green]\n\n"
                f"States captured: {stats['states_captured']}\n"
                f"Targets discovered: {stats['total_targets']}\n"
                f"Visited: {stats['visited']} | Skipped: {stats['skipped']} | Failed: {stats['failed']}\n"
                f"Budget used: {stats['budget_used']} / {self.engine.state.budget_total}\n"
                f"Steps: {stats['steps']}\n\n"
                f"Artifacts:\n"
                f"  inventory.json, sitemap.json, site_hierarchy.json\n"
                f"  operation_trace.json, run_log.jsonl\n"
                f"  run_timing_summary.json\n"
                f"  run_observe_breakdown.json\n"
                f"  exploration_report.md\n"
                f"  operation_trace.md\n"
                f"  site_hierarchy.md\n"
                f"  {self.engine.config.synthesis.ux_report_filename_md}\n"
                f"  {len(self.engine._analysis_results)} state analyses\n"
                f"  {len(self.engine._page_insights)} page insights\n"
                f"  {len(self.engine._extraction_results)} extraction results",
                title="Summary",
            )
        )

    def observe_breakdown_summary(self) -> dict[str, object]:
        entries = list(self.engine._observe_breakdown_entries)
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

    def build_extraction_summary(self, extraction_rows: list[dict]) -> dict[str, int]:
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
