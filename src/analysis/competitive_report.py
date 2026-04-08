"""Competitive analysis generator and typed outputs."""

from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from src.agent.state import AgentState


class CompetitiveSummary(BaseModel):
    product_category_guess: str = "unknown"
    admin_maturity_score: float = 0.0
    data_density_score: float = 0.0
    workflow_complexity_score: float = 0.0
    observed_strengths: list[str] = Field(default_factory=list)
    observed_gaps: list[str] = Field(default_factory=list)
    key_differentiators: list[str] = Field(default_factory=list)


class CompetitiveAnalysis(BaseModel):
    target: str
    run_metadata: dict = Field(default_factory=dict)
    site_structure_summary: dict = Field(default_factory=dict)
    page_type_distribution: dict[str, int] = Field(default_factory=dict)
    feature_modules: list[dict] = Field(default_factory=list)
    data_entities: list[dict] = Field(default_factory=list)
    interaction_patterns: list[dict] = Field(default_factory=list)
    design_system_signals: dict = Field(default_factory=dict)
    evidence_index: list[dict] = Field(default_factory=list)
    competitive_summary: CompetitiveSummary = Field(default_factory=CompetitiveSummary)
    comparison_notes: list[str] = Field(default_factory=list)


class CompetitiveReportGenerator:
    """Aggregates artifacts into competitive-analysis outputs."""

    def generate(
        self,
        state: AgentState,
        analysis_results: dict[str, dict] | None = None,
        page_insights: dict[str, dict] | None = None,
        extraction_results: dict[str, dict] | None = None,
    ) -> CompetitiveAnalysis:
        """Generate the structured competitive-analysis object."""
        analysis_results = analysis_results or {}
        page_insights = page_insights or {}
        extraction_results = extraction_results or {}
        unique_page_insights = self._unique_page_insights(page_insights)

        page_type_distribution = self._page_type_distribution(unique_page_insights)
        feature_modules = self._feature_modules(unique_page_insights, extraction_results)
        data_entities = self._data_entities(extraction_results)
        interaction_patterns = self._interaction_patterns(unique_page_insights)
        design_system_signals = self._design_system_signals(analysis_results)
        evidence_index = self._evidence_index(state, unique_page_insights, extraction_results)
        summary = self._competitive_summary(state, page_type_distribution, extraction_results)

        return CompetitiveAnalysis(
            target=self._target_label(state),
            run_metadata={
                "total_targets": len(state.targets),
                "states_captured": len(state.states),
                "visited_routes": sum(
                    1 for target in state.targets.values()
                    if target.target_type.value == "route" and target.id in state.visited
                ),
                "budget_used": state.budget_total - state.budget_remaining,
            },
            site_structure_summary={
                "route_count": sum(1 for target in state.targets.values() if target.target_type.value == "route"),
                "interaction_count": sum(1 for target in state.targets.values() if target.target_type.value != "route"),
                "depth_max": max((target.depth for target in state.targets.values()), default=0),
            },
            page_type_distribution=page_type_distribution,
            feature_modules=feature_modules,
            data_entities=data_entities,
            interaction_patterns=interaction_patterns,
            design_system_signals=design_system_signals,
            evidence_index=evidence_index,
            competitive_summary=summary,
            comparison_notes=self._comparison_notes(summary, page_type_distribution),
        )

    def _unique_page_insights(self, page_insights: dict[str, dict]) -> list[dict]:
        """Deduplicate page insights by URL, preferring captured states over observe placeholders."""
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

    def generate_markdown(self, analysis: CompetitiveAnalysis) -> str:
        """Generate the markdown competitive-analysis report."""
        lines = [
            "# Competitive Analysis",
            "",
            "## Executive Summary",
            f"- **Target:** {analysis.target}",
            f"- **Product category guess:** {analysis.competitive_summary.product_category_guess}",
            f"- **Admin maturity score:** {analysis.competitive_summary.admin_maturity_score:.2f}",
            f"- **Data density score:** {analysis.competitive_summary.data_density_score:.2f}",
            f"- **Workflow complexity score:** {analysis.competitive_summary.workflow_complexity_score:.2f}",
            "",
            "## Site Structure",
            f"- Routes: {analysis.site_structure_summary.get('route_count', 0)}",
            f"- Interaction targets: {analysis.site_structure_summary.get('interaction_count', 0)}",
            f"- Max depth: {analysis.site_structure_summary.get('depth_max', 0)}",
            "",
            "## Page Type Distribution",
        ]

        for page_type, count in sorted(analysis.page_type_distribution.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"- **{page_type}**: {count}")

        lines.extend(["", "## Feature Modules"])
        for module in analysis.feature_modules[:10]:
            lines.append(f"- **{module.get('name', 'unknown')}**: {module.get('evidence_count', 0)} signals")

        lines.extend(["", "## Data Entities"])
        if analysis.data_entities:
            for entity in analysis.data_entities[:10]:
                lines.append(
                    f"- **{entity.get('name', 'unknown')}**: "
                    f"{entity.get('source_count', 0)} sources, {entity.get('example_count', 0)} examples"
                )
        else:
            lines.append("- No confident data entities extracted.")

        lines.extend(["", "## Interaction Patterns"])
        for pattern in analysis.interaction_patterns:
            lines.append(f"- **{pattern.get('name', 'unknown')}**: {pattern.get('count', 0)}")

        lines.extend(["", "## Design System Signals"])
        for key, value in analysis.design_system_signals.items():
            lines.append(f"- **{key}**: {value}")

        lines.extend(["", "## Observed Strengths"])
        for item in analysis.competitive_summary.observed_strengths:
            lines.append(f"- {item}")

        lines.extend(["", "## Observed Gaps"])
        for item in analysis.competitive_summary.observed_gaps:
            lines.append(f"- {item}")

        lines.extend(["", "## Competitive Positioning"])
        for item in analysis.comparison_notes:
            lines.append(f"- {item}")

        lines.extend(["", "## Evidence Index"])
        for item in analysis.evidence_index[:15]:
            lines.append(f"- `{item.get('url', '')}` -> {item.get('kind', 'unknown')}")

        return "\n".join(lines)

    def _target_label(self, state: AgentState) -> str:
        """Build target label from the first captured state."""
        first_state = next(iter(sorted(state.states.values(), key=lambda s: s.timestamp)), None)
        if not first_state:
            return "unknown"
        parsed = urlparse(first_state.url)
        return parsed.netloc or first_state.url

    def _page_type_distribution(self, page_insights: list[dict]) -> dict[str, int]:
        """Aggregate page types from page insights."""
        counter: Counter[str] = Counter()
        for insight in page_insights:
            page_type_vision = str(insight.get("page_type_vision") or "").strip()
            page_type_dom = str(insight.get("page_type_dom") or "").strip()
            page_type = page_type_vision if page_type_vision and page_type_vision != "unknown" else (page_type_dom or "unknown")
            counter[page_type] += 1
        return dict(counter)

    def _feature_modules(self, page_insights: list[dict],
                         extraction_results: dict[str, dict]) -> list[dict]:
        """Infer feature modules from paths and insights."""
        module_counter: Counter[str] = Counter()

        for insight in page_insights:
            url = str(insight.get("url", ""))
            path = self._module_path_from_url(url)
            top = path.split("/")[0] if path else "root"
            module_counter[top] += 1

        return [
            {"name": name, "evidence_count": count}
            for name, count in module_counter.most_common(10)
        ]

    def _module_path_from_url(self, url: str) -> str:
        """Infer a module path from either URL path or hash-router fragment."""
        parsed = urlparse(url)
        fragment = parsed.fragment.strip()
        if fragment:
            fragment_path = fragment.split("?", 1)[0].strip("/")
            if fragment_path:
                return fragment_path

        return parsed.path.strip("/") or "root"

    def _data_entities(self, extraction_results: dict[str, dict]) -> list[dict]:
        """Infer likely data entities from extraction outputs."""
        entity_counter: dict[str, dict[str, int]] = {}

        for result in extraction_results.values():
            strategy = str(result.get("strategy", "unknown"))
            if strategy == "list_table":
                headers = result.get("summary", {}).get("headers", [])
                for header in headers[:8]:
                    name = str(header).strip()
                    if not name:
                        continue
                    entity_counter.setdefault(name, {"source_count": 0, "example_count": 0})
                    entity_counter[name]["source_count"] += 1
                    entity_counter[name]["example_count"] += len(result.get("records", []))
            elif strategy in {"detail_fields", "form_schema"}:
                fields = result.get("fields", [])
                for field in fields[:10]:
                    name = str(field.get("label") or field.get("name") or "").strip()
                    if not name:
                        continue
                    entity_counter.setdefault(name, {"source_count": 0, "example_count": 0})
                    entity_counter[name]["source_count"] += 1
                    entity_counter[name]["example_count"] += 1

        ranked = sorted(
            entity_counter.items(),
            key=lambda item: (-item[1]["source_count"], -item[1]["example_count"], item[0]),
        )
        return [
            {
                "name": name,
                "source_count": counts["source_count"],
                "example_count": counts["example_count"],
            }
            for name, counts in ranked[:15]
        ]

    def _interaction_patterns(self, page_insights: list[dict]) -> list[dict]:
        """Summarize interaction patterns from page insights."""
        counter: Counter[str] = Counter()
        for insight in page_insights:
            for tag in insight.get("analysis_tags", []):
                counter[str(tag)] += 1
        return [{"name": name, "count": count} for name, count in counter.most_common()]

    def _design_system_signals(self, analysis_results: dict[str, dict]) -> dict:
        """Aggregate design system and tech-stack signals."""
        framework_counter: Counter[str] = Counter()
        ui_counter: Counter[str] = Counter()

        for result in analysis_results.values():
            tech = result.get("tech_stack", {})
            framework = tech.get("framework")
            ui_library = tech.get("ui_library")
            if framework:
                framework_counter[str(framework)] += 1
            if ui_library:
                ui_counter[str(ui_library)] += 1

        return {
            "frameworks": dict(framework_counter),
            "ui_libraries": dict(ui_counter),
            "primary_framework": framework_counter.most_common(1)[0][0] if framework_counter else "unknown",
            "primary_ui_library": ui_counter.most_common(1)[0][0] if ui_counter else "unknown",
        }

    def _evidence_index(self, state: AgentState, page_insights: list[dict],
                        extraction_results: dict[str, dict]) -> list[dict]:
        """Build a compact evidence index for the final report."""
        items: list[dict] = []

        for snapshot in sorted(state.states.values(), key=lambda s: s.timestamp):
            items.append({
                "state_id": snapshot.id,
                "url": snapshot.url,
                "kind": "capture",
                "screenshot": snapshot.screenshot_path,
                "html": snapshot.html_path,
            })

        for insight in page_insights:
            items.append({
                "state_id": insight.get("state_id", ""),
                "url": insight.get("url", ""),
                "kind": "page_insight",
                "page_type": (
                    insight.get("page_type_vision")
                    if insight.get("page_type_vision") not in {"", None, "unknown"}
                    else insight.get("page_type_dom")
                ) or "unknown",
            })

        for state_id, result in extraction_results.items():
            items.append({
                "state_id": state_id,
                "url": result.get("url", ""),
                "kind": "extraction",
                "strategy": result.get("strategy", "unknown"),
                "status": result.get("status", "unknown"),
            })

        return items

    def _competitive_summary(self, state: AgentState, page_type_distribution: dict[str, int],
                             extraction_results: dict[str, dict]) -> CompetitiveSummary:
        """Generate the top-level competitive summary."""
        route_count = sum(1 for target in state.targets.values() if target.target_type.value == "route")
        successful_extractions = sum(1 for result in extraction_results.values() if result.get("status") == "success")
        list_pages = page_type_distribution.get("list", 0)
        form_pages = page_type_distribution.get("form", 0) + page_type_distribution.get("modal", 0)
        detail_pages = page_type_distribution.get("detail", 0)
        dashboard_pages = page_type_distribution.get("dashboard", 0)

        admin_maturity = min(1.0, (route_count / 20) + (form_pages / 20) + (detail_pages / 20))
        data_density = min(1.0, (list_pages / 12) + (successful_extractions / 20))
        workflow_complexity = min(1.0, (form_pages / 15) + (detail_pages / 15) + (dashboard_pages / 20))

        strengths: list[str] = []
        gaps: list[str] = []
        differentiators: list[str] = []

        if list_pages > 0:
            strengths.append("Observed structured list/table surfaces, suggesting operational data workflows.")
        if form_pages > 0:
            strengths.append("Observed configuration or CRUD form surfaces, indicating editable product workflows.")
        if detail_pages > 0:
            strengths.append("Observed detail-oriented views, suggesting entity-centric product organization.")
        if successful_extractions == 0:
            gaps.append("No successful structured extraction yet; entity understanding remains shallow.")
        if route_count < 5:
            gaps.append("Limited discovered route surface; competitive conclusions may be incomplete.")

        differentiators.append("Evidence-backed recon and extraction artifacts support auditability beyond generic agent transcripts.")
        if successful_extractions > 0:
            differentiators.append("Structured extraction enables downstream benchmarking and entity-level product comparison.")

        category = "admin_saas"
        if dashboard_pages > list_pages and dashboard_pages > form_pages:
            category = "dashboard_or_analytics"
        elif form_pages > 0 and detail_pages > 0:
            category = "admin_crud_platform"

        return CompetitiveSummary(
            product_category_guess=category,
            admin_maturity_score=round(admin_maturity, 2),
            data_density_score=round(data_density, 2),
            workflow_complexity_score=round(workflow_complexity, 2),
            observed_strengths=strengths,
            observed_gaps=gaps,
            key_differentiators=differentiators,
        )

    def _comparison_notes(self, summary: CompetitiveSummary,
                          page_type_distribution: dict[str, int]) -> list[str]:
        """Build comparison-oriented notes for the final report."""
        notes = [
            "This system emphasizes evidence-backed competitive analysis over generic browser task completion.",
            "Compared with prompt-first browser agents, the artifact trail here is better suited for audit and review.",
        ]
        if summary.data_density_score >= 0.5:
            notes.append("The target shows meaningful data-dense surfaces, making structured extraction a strong differentiator.")
        if page_type_distribution.get("dashboard", 0) > 0:
            notes.append("Dashboard coverage suggests analytics or operational overview capabilities worth benchmarking against peers.")
        if summary.workflow_complexity_score >= 0.5:
            notes.append("Workflow complexity appears moderate to high, so product comparison should include CRUD and configuration depth.")
        return notes
