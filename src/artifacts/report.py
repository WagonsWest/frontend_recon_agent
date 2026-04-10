"""Report generator — produces human-readable exploration report."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.agent.state import AgentState, VisitStatus, TargetType, PageCoverage


class ReportGenerator:
    """Generates final markdown exploration report."""

    def generate(self, state: AgentState, start_time: str, end_time: str,
                 analysis_results: dict[str, dict] | None = None,
                 page_insights: dict[str, dict] | None = None,
                 extraction_results: dict[str, dict] | None = None) -> str:
        """Generate comprehensive exploration report."""
        stats = state.get_stats()

        sections = [
            self._header(state, start_time, end_time, stats),
            self._site_architecture(state),
            self._page_coverage(state),
            self._page_patterns(state, analysis_results),
            self._page_semantics(page_insights),
            self._extraction_summary(extraction_results),
            self._coverage_gaps(state),
            self._artifacts_section(state, stats),
        ]

        return "\n\n".join(sections)

    def _unique_page_insights(self, page_insights: dict[str, dict] | None) -> list[dict]:
        """Deduplicate page insights by URL, preferring captured states over observe placeholders."""
        if not page_insights:
            return []

        deduped: dict[str, dict] = {}
        for state_id, insight in page_insights.items():
            url = str(insight.get("url", "")).strip() or state_id
            existing = deduped.get(url)
            if existing is None:
                deduped[url] = insight
                continue

            existing_id = str(existing.get("state_id", ""))
            candidate_id = str(insight.get("state_id", ""))
            if existing_id.startswith("observe_") and not candidate_id.startswith("observe_"):
                deduped[url] = insight

        return list(deduped.values())

    def _header(self, state: AgentState, start_time: str, end_time: str, stats: dict) -> str:
        """Run summary header."""
        # Calculate duration
        try:
            t_start = datetime.fromisoformat(start_time)
            t_end = datetime.fromisoformat(end_time)
            duration = str(t_end - t_start).split(".")[0]
        except Exception:
            duration = "unknown"

        success_count = sum(1 for s in state.states.values() if s.visit_status == VisitStatus.SUCCESS)
        skipped_count = len(state.skipped)
        failed_count = len(state.failed)
        route_count = sum(1 for t in state.targets.values() if t.target_type == TargetType.ROUTE and t.id in state.visited)
        interaction_count = sum(1 for t in state.targets.values() if t.target_type != TargetType.ROUTE and t.id in state.visited)

        return f"""# Exploration Report

## Run Summary
- **Duration:** {duration}
- **States captured:** {success_count} / {state.budget_total} budget
- **States skipped (low novelty):** {skipped_count}
- **Failed:** {failed_count}
- **Unique routes visited:** {route_count}
- **Interaction states:** {interaction_count}
- **Total targets discovered:** {stats['total_targets']}
- **Steps executed:** {stats['steps']}"""

    def _site_architecture(self, state: AgentState) -> str:
        """Build site architecture tree."""
        lines = ["## Site Architecture", ""]

        # Build tree from route targets
        root_targets = [t for t in state.targets.values()
                       if t.target_type == TargetType.ROUTE and t.parent_id is None]

        # Group by parent
        children_map: dict[str | None, list] = {}
        for t in state.targets.values():
            if t.target_type == TargetType.ROUTE:
                children_map.setdefault(t.parent_id, []).append(t)

        def render_tree(parent_id: str | None, indent: int = 0):
            children = children_map.get(parent_id, [])
            for child in sorted(children, key=lambda t: t.label):
                status = "v" if child.id in state.visited else "o" if child.id in state.skipped else "x"
                prefix = "  " * indent
                lines.append(f"{prefix}- [{status}] {child.label}")
                render_tree(child.id, indent + 1)

        render_tree(None)

        if len(lines) == 2:
            # Flat list fallback
            for t in sorted(state.targets.values(), key=lambda t: t.depth):
                if t.target_type == TargetType.ROUTE and t.id in state.visited:
                    lines.append(f"- {t.label} ({t.locator})")

        return "\n".join(lines)

    def _page_coverage(self, state: AgentState) -> str:
        """Per-page coverage summary showing what was found vs explored."""
        lines = ["## Per-Page Coverage", ""]

        if not state.coverage:
            lines.append("_No coverage data available._")
            return "\n".join(lines)

        # Separate pages with gaps from fully covered
        pages_with_gaps = []
        pages_covered = []

        for target_id, cov in state.coverage.items():
            target = state.targets.get(target_id)
            if not target or target.target_type != TargetType.ROUTE:
                continue
            if cov.has_unexplored:
                pages_with_gaps.append((target, cov))
            else:
                pages_covered.append((target, cov))

        if pages_with_gaps:
            lines.append("### Pages with Unexplored Interactions")
            lines.append("")
            for target, cov in sorted(pages_with_gaps, key=lambda x: x[0].label):
                lines.append(f"**{target.label}** (`{cov.page_url}`)")
                if cov.action_buttons_found > 0:
                    lines.append(f"- Action buttons: {cov.action_buttons_found} found, {cov.action_buttons_clicked} clicked")
                if cov.dropdown_items_found > 0:
                    explored = cov.dropdown_items_explored
                    skipped = cov.dropdown_items_skipped_novelty
                    found = cov.dropdown_items_found
                    parts = [f"{found} found", f"{explored} captured"]
                    if skipped:
                        parts.append(f"{skipped} skipped (similar)")
                    lines.append(f"- Dropdown items: {', '.join(parts)}")
                    if cov.dropdown_item_labels:
                        for label in cov.dropdown_item_labels:
                            lines.append(f"  - `{label}`")
                if cov.add_buttons_found > 0:
                    clicked = cov.add_buttons_clicked
                    skipped = cov.add_buttons_skipped_novelty
                    parts = [f"{cov.add_buttons_found} found", f"{clicked} captured"]
                    if skipped:
                        parts.append(f"{skipped} skipped (similar)")
                    lines.append(f"- Add/create buttons: {', '.join(parts)}")
                if cov.tabs_found > 0:
                    switched = cov.tabs_switched
                    skipped = cov.tabs_skipped_novelty
                    parts = [f"{cov.tabs_found} found", f"{switched} captured"]
                    if skipped:
                        parts.append(f"{skipped} skipped (similar)")
                    lines.append(f"- Tabs: {', '.join(parts)}")
                    if cov.tab_labels:
                        for label in cov.tab_labels:
                            lines.append(f"  - `{label}`")
                if cov.expand_rows_found > 0:
                    expanded = cov.expand_rows_expanded
                    skipped = cov.expand_rows_skipped_novelty
                    parts = [f"{cov.expand_rows_found} found", f"{expanded} captured"]
                    if skipped:
                        parts.append(f"{skipped} skipped (similar)")
                    lines.append(f"- Expandable rows: {', '.join(parts)}")
                lines.append("")

        # Summary stats
        total_pages = len(pages_with_gaps) + len(pages_covered)
        lines.append(f"### Coverage Summary")
        lines.append(f"- **{len(pages_covered)}/{total_pages}** pages fully covered")
        lines.append(f"- **{len(pages_with_gaps)}/{total_pages}** pages have unexplored interactions")

        return "\n".join(lines)

    def _page_patterns(self, state: AgentState, analysis_results: dict[str, dict] | None) -> str:
        """Summarize detected page patterns."""
        lines = ["## Page Patterns", ""]

        if not analysis_results:
            lines.append("_No per-state analysis available._")
            return "\n".join(lines)

        # Aggregate component types across all analyzed states
        component_counter: dict[str, int] = {}
        layout_patterns: dict[str, int] = {}

        for state_id, analysis in analysis_results.items():
            for comp_type in analysis.get("component_types", []):
                component_counter[comp_type] = component_counter.get(comp_type, 0) + 1
            layout = analysis.get("layout_pattern", "")
            if layout:
                layout_patterns[layout] = layout_patterns.get(layout, 0) + 1

        total = len(analysis_results)
        for comp, count in sorted(component_counter.items(), key=lambda x: -x[1]):
            lines.append(f"- **{comp}**: found in {count}/{total} analyzed states")

        if layout_patterns:
            lines.append("")
            lines.append("### Layout Patterns")
            for layout, count in sorted(layout_patterns.items(), key=lambda x: -x[1]):
                lines.append(f"- {layout}: {count} pages")

        return "\n".join(lines)

    def _coverage_gaps(self, state: AgentState) -> str:
        """Report what was NOT explored."""
        lines = ["## Coverage Gaps", ""]

        # Targets that were discovered but never visited
        unvisited = [t for t in state.targets.values()
                    if t.id not in state.visited and t.id not in state.skipped]

        if unvisited:
            lines.append("### Discovered but Not Visited")
            for t in unvisited:
                lines.append(f"- {t.label} ({t.target_type.value}, depth {t.depth})")

        # Failed targets
        if state.failed:
            lines.append("")
            lines.append("### Failed Targets")
            for tid, retries in state.failed.items():
                t = state.targets.get(tid)
                label = t.label if t else tid
                lines.append(f"- {label}: failed after {retries} retries")

        # Skipped targets
        skipped_targets = [state.targets[tid] for tid in state.skipped if tid in state.targets]
        if skipped_targets:
            lines.append("")
            lines.append("### Skipped (Low Novelty)")
            for t in skipped_targets:
                lines.append(f"- {t.label} ({t.target_type.value})")

        if len(lines) == 2:
            lines.append("_All discovered targets were visited._")

        return "\n".join(lines)

    def _page_semantics(self, page_insights: dict[str, dict] | None) -> str:
        """Summarize page semantics from DOM and vision understanding."""
        lines = ["## Page Semantics", ""]

        if not page_insights:
            lines.append("_No page insight artifacts available._")
            return "\n".join(lines)

        page_type_counter: dict[str, int] = {}
        mismatch_lines: list[str] = []

        for insight in self._unique_page_insights(page_insights):
            page_type_vision = insight.get("page_type_vision")
            page_type_dom = insight.get("page_type_dom", "unknown")
            page_type = page_type_vision if page_type_vision and page_type_vision != "unknown" else page_type_dom
            page_type_counter[page_type] = page_type_counter.get(page_type, 0) + 1

            page_type_vision = insight.get("page_type_vision", "unknown")
            if page_type_vision != "unknown" and page_type_dom != page_type_vision:
                mismatch_lines.append(
                    f"- `{insight.get('url', '')}`: DOM={page_type_dom}, vision={page_type_vision}"
                )

        lines.append("### Vision/DOM Page Type Distribution")
        for page_type, count in sorted(page_type_counter.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"- **{page_type}**: {count} pages")

        if mismatch_lines:
            lines.append("")
            lines.append("### DOM/Vision Differences")
            lines.extend(mismatch_lines[:10])

        return "\n".join(lines)

    def _extraction_summary(self, extraction_results: dict[str, dict] | None) -> str:
        """Summarize structured extraction outputs."""
        lines = ["## Structured Extraction", ""]

        if not extraction_results:
            lines.append("_No extraction results available._")
            return "\n".join(lines)

        status_counts: dict[str, int] = {}
        strategy_counts: dict[str, int] = {}

        for result in extraction_results.values():
            status = str(result.get("status", "unknown"))
            strategy = str(result.get("strategy", "unknown"))
            status_counts[status] = status_counts.get(status, 0) + 1
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

        lines.append("### Status")
        for status, count in sorted(status_counts.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"- **{status}**: {count}")

        lines.append("")
        lines.append("### Strategies")
        for strategy, count in sorted(strategy_counts.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"- **{strategy}**: {count}")

        sample_results = [
            result for result in extraction_results.values()
            if result.get("status") == "success"
        ][:5]
        if sample_results:
            lines.append("")
            lines.append("### Sample Successful Extractions")
            for result in sample_results:
                url = result.get("url", "")
                strategy = result.get("strategy", "unknown")
                capture_label = result.get("capture_label", "")
                capture_context = result.get("capture_context", "")
                summary = result.get("summary", {})
                context_suffix = (
                    f" [{capture_context}: {capture_label}]"
                    if capture_label or capture_context else ""
                )
                lines.append(f"- `{url}` via **{strategy}**{context_suffix}: {summary}")

        return "\n".join(lines)

    def _artifacts_section(self, state: AgentState, stats: dict) -> str:
        """List generated artifacts."""
        return f"""## Artifacts
- **inventory.json**: {stats['states_captured']} entries
- **sitemap.json**: {stats['total_targets']} nodes, {len(state.edges)} edges
- **run_log.jsonl**: {stats['steps']} steps
- **run_timing_summary.json**: aggregated timing by phase and action
- **analysis/**: per-state analysis files
- **vision/**: per-page vision understanding artifacts
- **page_insights/**: merged DOM + vision page semantics
- **dataset.jsonl**: per-state structured extraction results
- **dataset_summary.json**: extraction aggregate statistics
- **extraction_failures.json**: empty/failed extraction cases
- **ux_report.md**: reviewer-style UX report grounded in runtime artifacts"""
