"""Competitive analysis generator and typed outputs."""

from __future__ import annotations

from collections import Counter
import re
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from src.agent.state import AgentState


class CompetitiveSummary(BaseModel):
    product_category_guess: str = "unknown"
    product_thesis: str = ""
    application_surface_score: float = 0.0
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
    route_family_distribution: list[dict] = Field(default_factory=list)
    primary_entry_points: list[str] = Field(default_factory=list)
    product_pillars: list[dict] = Field(default_factory=list)
    feature_modules: list[dict] = Field(default_factory=list)
    data_entities: list[dict] = Field(default_factory=list)
    interaction_patterns: list[dict] = Field(default_factory=list)
    design_system_signals: dict = Field(default_factory=dict)
    evidence_index: list[dict] = Field(default_factory=list)
    competitive_summary: CompetitiveSummary = Field(default_factory=CompetitiveSummary)
    coverage_notes: list[str] = Field(default_factory=list)
    comparison_notes: list[str] = Field(default_factory=list)


class CompetitiveSynthesis(BaseModel):
    executive_summary: str = ""
    product_positioning: list[str] = Field(default_factory=list)
    key_workflows: list[str] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)
    risks_and_unknowns: list[str] = Field(default_factory=list)
    recommended_followups: list[str] = Field(default_factory=list)
    markdown_report: str = ""


class CompetitiveReportGenerator:
    """Aggregates artifacts into competitive-analysis outputs."""

    PRODUCT_PILLAR_RULES = [
        (
            "Benchmarking and index surfaces",
            ("benchmark", "benchmarking", "index", "intelligence index", "openness index", "coding index"),
        ),
        (
            "Model analysis and provider comparison",
            ("model", "models", "provider", "pricing", "price", "performance analysis", "compare provider"),
        ),
        (
            "Evaluation methodology and benchmark design",
            ("methodology", "evaluation", "evaluations", "testing", "hallucination", "reasoning", "benchmark"),
        ),
        (
            "Leaderboards, arenas, and trend tracking",
            ("leaderboard", "leaderboards", "arena", "arenas", "trend", "trends", "hardware"),
        ),
    ]

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
        route_family_distribution = self._route_family_distribution(state)
        primary_entry_points = self._primary_entry_points(extraction_results)
        product_pillars = self._product_pillars(state, extraction_results)
        feature_modules = self._feature_modules(unique_page_insights, extraction_results)
        data_entities = self._data_entities(extraction_results)
        interaction_patterns = self._interaction_patterns(unique_page_insights)
        design_system_signals = self._design_system_signals(analysis_results)
        evidence_index = self._evidence_index(state, unique_page_insights, extraction_results)
        coverage_notes = self._coverage_notes(
            state,
            page_type_distribution,
            extraction_results,
            route_family_distribution,
        )
        summary = self._competitive_summary(
            state,
            page_type_distribution,
            extraction_results,
            route_family_distribution,
            product_pillars,
            primary_entry_points,
        )

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
            route_family_distribution=route_family_distribution,
            primary_entry_points=primary_entry_points,
            product_pillars=product_pillars,
            feature_modules=feature_modules,
            data_entities=data_entities,
            interaction_patterns=interaction_patterns,
            design_system_signals=design_system_signals,
            evidence_index=evidence_index,
            competitive_summary=summary,
            coverage_notes=coverage_notes,
            comparison_notes=self._comparison_notes(summary, route_family_distribution, coverage_notes),
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
            f"- **Product thesis:** {analysis.competitive_summary.product_thesis}",
            f"- **Application surface score:** {analysis.competitive_summary.application_surface_score:.2f}",
            f"- **Data density score:** {analysis.competitive_summary.data_density_score:.2f}",
            f"- **Workflow complexity score:** {analysis.competitive_summary.workflow_complexity_score:.2f}",
            "",
            "## Site Structure",
            f"- Routes: {analysis.site_structure_summary.get('route_count', 0)}",
            f"- Interaction targets: {analysis.site_structure_summary.get('interaction_count', 0)}",
            f"- Max depth: {analysis.site_structure_summary.get('depth_max', 0)}",
            "",
            "## Route Family Distribution",
        ]

        for family in analysis.route_family_distribution[:8]:
            lines.append(
                f"- **{family.get('name', 'unknown')}**: {family.get('count', 0)} "
                f"visited capture(s), share {family.get('share', 0)}"
            )

        lines.extend(["", "## Page Type Distribution"])
        for page_type, count in sorted(analysis.page_type_distribution.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"- **{page_type}**: {count}")

        lines.extend(["", "## Primary Entry Points"])
        if analysis.primary_entry_points:
            for item in analysis.primary_entry_points[:10]:
                lines.append(f"- {item}")
        else:
            lines.append("- No strong public entry points were extracted from the current run.")

        lines.extend(["", "## Product Pillars"])
        if analysis.product_pillars:
            for pillar in analysis.product_pillars[:6]:
                examples = ", ".join(f"`{item}`" for item in pillar.get("examples", [])[:3])
                details = f": {examples}" if examples else ""
                lines.append(
                    f"- **{pillar.get('name', 'unknown')}**: "
                    f"{pillar.get('evidence_count', 0)} evidence hit(s){details}"
                )
        else:
            lines.append("- No stable product pillars were inferred from the current evidence.")

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

        content_evidence = self._content_evidence(analysis.evidence_index)
        lines.extend(["", "## Content Evidence"])
        if content_evidence:
            for item in content_evidence:
                lines.append(f"- `{item.get('url', '')}`: {item.get('summary', '')}")
        else:
            lines.append("- No structured content-block evidence extracted yet.")

        evidence_samples = self._evidence_samples(analysis.evidence_index)
        lines.extend(["", "## Evidence Samples"])
        if evidence_samples:
            for item in evidence_samples:
                lines.append(
                    f"- **{item.get('kind', 'unknown')}** [{item.get('role', '')}] "
                    f"`{item.get('url', '')}`: {item.get('text', '')}"
                )
        else:
            lines.append("- No page-level evidence samples available.")

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

        lines.extend(["", "## Coverage Notes"])
        for item in analysis.coverage_notes:
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

    def _route_family_distribution(self, state: AgentState) -> list[dict]:
        """Summarize which visited route families dominate captured evidence."""
        counter: Counter[str] = Counter()
        examples: dict[str, list[str]] = {}
        total = 0

        for snapshot in sorted(state.states.values(), key=lambda item: item.timestamp):
            target = state.targets.get(snapshot.target_id)
            if target and target.target_type.value != "route":
                continue
            family = self._route_family_from_url(snapshot.url)
            counter[family] += 1
            total += 1
            label = target.label if target else self._module_path_from_url(snapshot.url)
            if label:
                examples.setdefault(family, [])
                if label not in examples[family]:
                    examples[family].append(label)

        if total == 0:
            return []

        return [
            {
                "name": family,
                "count": count,
                "share": round(count / total, 2),
                "examples": examples.get(family, [])[:3],
            }
            for family, count in counter.most_common()
        ]

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

        path = parsed.path.strip("/")
        if not path:
            return "root"

        parts = [part for part in path.split("/") if part]
        if parts and parts[0].isdigit():
            if len(parts) > 1:
                return "/".join(parts[1:])
            if parsed.netloc.startswith("docs."):
                return "docs"
        return path

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
            elif strategy == "content_blocks":
                evidence_units = result.get("evidence_units", [])
                if evidence_units:
                    for unit in evidence_units[:20]:
                        if str(unit.get("kind", "")) != "content_section":
                            continue
                        name = str(unit.get("normalized_text") or unit.get("raw_text") or "").strip()
                        if not name:
                            continue
                        entity_counter.setdefault(name, {"source_count": 0, "example_count": 0})
                        entity_counter[name]["source_count"] += 1
                        entity_counter[name]["example_count"] += 1
                else:
                    for record in result.get("records", []):
                        if record.get("kind") == "content_sections":
                            for item in record.get("items", [])[:8]:
                                name = str(item.get("title") or "").strip()
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

    def _primary_entry_points(self, extraction_results: dict[str, dict]) -> list[str]:
        """Extract likely user-facing entry points from landing/content surfaces."""
        ranked_results = sorted(
            extraction_results.values(),
            key=lambda result: (
                0 if str(result.get("page_type", "")) == "landing" else 1,
                0 if str(result.get("capture_label", "")) == "root" else 1,
                str(result.get("url", "")),
            ),
        )
        ranked_labels: dict[str, int] = {}
        ordered: list[str] = []

        for result in ranked_results:
            if str(result.get("strategy", "")) != "content_blocks":
                continue
            for kind in ("primary_ctas", "nav_items"):
                for item in self._record_items(result, kind):
                    label = self._normalize_report_text(str(item.get("label") or item or ""))
                    if not self._is_report_worthy_text(label):
                        continue
                    if kind == "nav_items" and label.lower() == "artificial analysis":
                        continue
                    if kind == "primary_ctas":
                        score = 3 if str(result.get("page_type", "")) == "landing" else 1
                    else:
                        score = 1 if str(result.get("page_type", "")) == "landing" else 0
                    ranked_labels[label] = ranked_labels.get(label, 0) + score
                    if label not in ordered:
                        ordered.append(label)

        return sorted(ordered, key=lambda label: (-ranked_labels.get(label, 0), ordered.index(label)))[:6]

    def _product_pillars(self, state: AgentState, extraction_results: dict[str, dict]) -> list[dict]:
        """Infer higher-level product pillars from extracted text and visited surfaces."""
        texts = self._analysis_texts(state, extraction_results)
        pillars: list[dict] = []

        for name, keywords in self.PRODUCT_PILLAR_RULES:
            matches: list[str] = []
            for text in texts:
                lowered = text.lower()
                if any(keyword in lowered for keyword in keywords):
                    if text not in matches:
                        matches.append(text)
            if not matches:
                continue
            pillars.append({
                "name": name,
                "evidence_count": len(matches),
                "examples": matches[:3],
            })

        return sorted(
            pillars,
            key=lambda item: (-int(item.get("evidence_count", 0)), str(item.get("name", ""))),
        )[:4]

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
            item = {
                "state_id": state_id,
                "url": result.get("url", ""),
                "kind": "extraction",
                "strategy": result.get("strategy", "unknown"),
                "status": result.get("status", "unknown"),
            }
            if result.get("strategy") == "content_blocks":
                item["summary"] = self._content_result_summary(result)
            items.append(item)

            for unit in result.get("evidence_units", [])[:12]:
                items.append({
                    "state_id": state_id,
                    "url": result.get("url", ""),
                    "kind": str(unit.get("kind", "evidence_unit")),
                    "role": str(unit.get("role", "")),
                    "text": str(unit.get("normalized_text") or unit.get("raw_text") or ""),
                    "locator": str(unit.get("locator", "")),
                    "confidence": unit.get("confidence", 0.0),
                })

        return items

    def _content_result_summary(self, result: dict) -> str:
        summary = result.get("summary", {}) or {}
        parts: list[str] = []
        hero_count = int(summary.get("hero_title_count", 0) or 0)
        cta_count = int(summary.get("primary_cta_count", 0) or 0)
        section_count = int(summary.get("content_section_count", 0) or 0)
        nav_count = int(summary.get("nav_item_count", 0) or 0)
        if hero_count:
            parts.append(f"{hero_count} hero titles")
        if cta_count:
            parts.append(f"{cta_count} CTAs")
        if section_count:
            parts.append(f"{section_count} sections")
        if nav_count:
            parts.append(f"{nav_count} nav items")
        return ", ".join(parts) or "content structure captured"

    def _content_evidence(self, evidence_index: list[dict]) -> list[dict]:
        return [
            item for item in evidence_index
            if item.get("kind") == "extraction" and item.get("strategy") == "content_blocks"
        ][:8]

    def _evidence_samples(self, evidence_index: list[dict]) -> list[dict]:
        return [
            item for item in evidence_index
            if item.get("kind") in {"hero", "cta", "nav_item", "content_section"} and item.get("text")
        ][:10]

    def _competitive_summary(self, state: AgentState, page_type_distribution: dict[str, int],
                             extraction_results: dict[str, dict],
                             route_family_distribution: list[dict],
                             product_pillars: list[dict],
                             primary_entry_points: list[str]) -> CompetitiveSummary:
        """Generate the top-level competitive summary."""
        route_count = sum(1 for target in state.targets.values() if target.target_type.value == "route")
        successful_extractions = sum(1 for result in extraction_results.values() if result.get("status") == "success")
        landing_pages = page_type_distribution.get("landing", 0)
        content_pages = page_type_distribution.get("content", 0)
        docs_pages = page_type_distribution.get("docs", 0)
        list_pages = page_type_distribution.get("list", 0)
        form_pages = (
            page_type_distribution.get("form", 0)
            + page_type_distribution.get("modal", 0)
            + page_type_distribution.get("auth", 0)
        )
        detail_pages = page_type_distribution.get("detail", 0)
        dashboard_pages = page_type_distribution.get("dashboard", 0)

        application_surface = min(1.0, (route_count / 20) + (form_pages / 20) + (detail_pages / 20))
        data_density = min(1.0, (list_pages / 12) + (successful_extractions / 20))
        workflow_complexity = min(1.0, (form_pages / 15) + (detail_pages / 15) + (dashboard_pages / 20))

        strengths: list[str] = []
        gaps: list[str] = []
        differentiators: list[str] = []
        top_family = route_family_distribution[0] if route_family_distribution else {}
        top_family_name = str(top_family.get("name", ""))
        top_family_share = float(top_family.get("share", 0.0))
        pillar_names = {str(item.get("name", "")) for item in product_pillars}

        if landing_pages > 0:
            strengths.append("Observed landing-style surfaces and user entry points, useful for product positioning.")
        if content_pages > 0:
            strengths.append("Observed content-oriented sections, suggesting an informational or community surface.")
        if docs_pages > 0:
            strengths.append("Observed documentation-like pages, indicating a knowledge-rich or developer-facing surface.")
        if list_pages > 0:
            strengths.append("Observed structured list/table surfaces, suggesting operational data workflows.")
        if form_pages > 0:
            strengths.append("Observed interactive form surfaces, indicating editable or guided product workflows.")
        if detail_pages > 0:
            strengths.append("Observed detail-oriented views, suggesting entity-centric product organization.")
        content_extractions = sum(
            1 for result in extraction_results.values() if result.get("strategy") == "content_blocks" and result.get("status") == "success"
        )

        if successful_extractions == 0:
            gaps.append("No successful structured extraction yet; entity understanding remains shallow.")
        elif content_extractions > 0:
            strengths.append("Structured content extraction captured navigational, CTA, or section-level evidence useful for competitive teardown.")
        if route_count < 5:
            gaps.append("Limited discovered route surface; competitive conclusions may be incomplete.")
        if top_family_share >= 0.6 and top_family_name:
            gaps.append(
                f"Visited evidence is concentrated in `{top_family_name}` pages, so conclusions may over-index on that surface family."
            )

        if "Evaluation methodology and benchmark design" in pillar_names:
            differentiators.append("Methodology transparency appears to be a visible trust-building differentiator.")
        if "Model analysis and provider comparison" in pillar_names:
            differentiators.append("Model-level analysis pages make comparison and benchmarking a first-class public surface.")
        if primary_entry_points:
            differentiators.append(
                "Public entry points expose multiple analytical lenses instead of a single generic homepage funnel."
            )

        category = "general_website"
        if {
            "Benchmarking and index surfaces",
            "Model analysis and provider comparison",
        }.issubset(pillar_names):
            category = "analysis_portal"
        elif docs_pages >= max(landing_pages, content_pages, list_pages, form_pages, dashboard_pages, 1):
            category = "developer_docs"
        elif landing_pages + content_pages >= max(list_pages + form_pages + dashboard_pages, 2):
            category = "content_or_marketing"
        elif dashboard_pages + list_pages + form_pages >= 3:
            category = "application_surface"
        elif form_pages >= 2 and landing_pages > 0:
            category = "onboarding_or_application_flow"
        elif list_pages + detail_pages >= 3:
            category = "application_ui"

        product_thesis = self._product_thesis(
            category,
            product_pillars,
            route_family_distribution,
            primary_entry_points,
        )

        return CompetitiveSummary(
            product_category_guess=category,
            product_thesis=product_thesis,
            application_surface_score=round(application_surface, 2),
            data_density_score=round(data_density, 2),
            workflow_complexity_score=round(workflow_complexity, 2),
            observed_strengths=strengths,
            observed_gaps=gaps,
            key_differentiators=differentiators,
        )

    def _product_thesis(
        self,
        category: str,
        product_pillars: list[dict],
        route_family_distribution: list[dict],
        primary_entry_points: list[str],
    ) -> str:
        """Build a compact thesis sentence grounded in observed public surfaces."""
        top_pillars = [str(item.get("name", "")) for item in product_pillars[:2] if item.get("name")]
        top_family = route_family_distribution[0] if route_family_distribution else {}
        top_family_name = str(top_family.get("name", ""))

        if category == "analysis_portal":
            return (
                "Current evidence suggests the target operates as a public analysis portal for AI systems, "
                "combining model-level comparisons, benchmark-oriented content, and methodology transparency."
            )
        if category == "developer_docs":
            return (
                "Current evidence suggests the target presents a documentation-heavy knowledge surface, "
                "with methodology and reference content carrying much of the explanatory load."
            )
        if category == "content_or_marketing":
            return (
                "Current evidence suggests the target behaves more like a public content and positioning surface "
                "than a workflow-heavy application UI."
            )
        if top_pillars:
            pillars_text = " and ".join(top_pillars[:2]).lower()
            return f"Current evidence suggests the target centers on {pillars_text}."
        if top_family_name:
            return f"Current evidence suggests the target is organized around `{top_family_name}` surfaces."
        if primary_entry_points:
            return (
                "Current evidence suggests the target exposes several public analytical entry points, "
                "but the overall product shape is still only partially observed."
            )
        return "Current evidence is still too sparse for a strong product thesis."

    def _coverage_notes(
        self,
        state: AgentState,
        page_type_distribution: dict[str, int],
        extraction_results: dict[str, dict],
        route_family_distribution: list[dict],
    ) -> list[str]:
        """Explain where the current crawl is likely biased or incomplete."""
        notes: list[str] = []
        total_results = len(extraction_results)
        successful_results = sum(1 for result in extraction_results.values() if result.get("status") == "success")
        top_family = route_family_distribution[0] if route_family_distribution else {}
        top_family_name = str(top_family.get("name", ""))
        top_family_share = float(top_family.get("share", 0.0))
        interactive_pages = (
            page_type_distribution.get("form", 0)
            + page_type_distribution.get("auth", 0)
            + page_type_distribution.get("modal", 0)
            + page_type_distribution.get("dashboard", 0)
        )

        if total_results and successful_results < total_results:
            notes.append(
                f"Only {successful_results}/{total_results} structured extractions were successful; many detail pages remained shallow."
            )
        if top_family_name and top_family_share >= 0.6:
            notes.append(
                f"{top_family_name} pages account for {int(top_family_share * 100)}% of captured route evidence, so the report may overweight that family."
            )
        if interactive_pages == 0:
            notes.append("This run covered public content/detail surfaces only; no authenticated or workflow-heavy product areas were observed.")
        if len(state.states) <= 10:
            notes.append("The capture budget was small, so this readout should be treated as directional rather than exhaustive.")
        return notes

    def _comparison_notes(
        self,
        summary: CompetitiveSummary,
        route_family_distribution: list[dict],
        coverage_notes: list[str],
    ) -> list[str]:
        """Build comparison-oriented notes for the final report."""
        notes: list[str] = []
        top_family = route_family_distribution[0] if route_family_distribution else {}
        top_family_name = str(top_family.get("name", ""))

        if summary.product_category_guess == "analysis_portal":
            notes.append("The target looks more like a public AI intelligence portal than a traditional developer-docs or CRUD application.")
        if "Methodology transparency appears to be a visible trust-building differentiator." in summary.key_differentiators:
            notes.append("Methodology depth appears to be part of the product positioning, not just supporting documentation.")
        if top_family_name == "models":
            notes.append("Model detail pages appear to be a major public comparison surface and likely deserve peer-by-peer benchmarking.")
        if coverage_notes:
            notes.append("Comparison against peers should control for the current crawl's surface skew before drawing strong product conclusions.")
        return notes

    def _analysis_texts(self, state: AgentState, extraction_results: dict[str, dict]) -> list[str]:
        texts: list[str] = []
        seen: set[str] = set()

        for snapshot in sorted(state.states.values(), key=lambda item: item.timestamp):
            target = state.targets.get(snapshot.target_id)
            for raw in [snapshot.title, target.label if target else ""]:
                text = self._normalize_report_text(str(raw))
                if self._is_report_worthy_text(text) and text not in seen:
                    seen.add(text)
                    texts.append(text)

        for result in extraction_results.values():
            for record_kind in ("hero_titles", "primary_ctas", "nav_items", "content_sections"):
                for item in self._record_items(result, record_kind):
                    if isinstance(item, dict):
                        raw = item.get("title") or item.get("label") or item.get("name") or ""
                    else:
                        raw = item
                    text = self._normalize_report_text(str(raw))
                    if self._is_report_worthy_text(text) and text not in seen:
                        seen.add(text)
                        texts.append(text)

        return texts

    def _record_items(self, result: dict, kind: str) -> list:
        for record in result.get("records", []):
            if str(record.get("kind", "")) == kind:
                items = record.get("items", [])
                return items if isinstance(items, list) else []
        return []

    def _route_family_from_url(self, url: str) -> str:
        path = self._module_path_from_url(url)
        if not path or path == "root":
            return "root"
        return path.split("/")[0]

    def _normalize_report_text(self, text: str) -> str:
        return " ".join(text.split()).strip()

    def _is_report_worthy_text(self, text: str) -> bool:
        if not text or len(text) < 2:
            return False
        if any(marker in text for marker in ["�", "鈱", "锟"]):
            return False
        if text.lower() in {"root", "unknown"}:
            return False
        if re.fullmatch(r"\d+\s*/\s*\d+", text):
            return False
        alnum_count = sum(char.isalnum() for char in text)
        if alnum_count == 0:
            return False
        if not any(char.isalpha() for char in text):
            return False
        weird_count = sum(
            1 for char in text
            if not (char.isalnum() or char.isspace() or char in "-_/&(),.:+'%")
        )
        if weird_count > 3 and weird_count >= alnum_count:
            return False
        if len(text) <= 4 and not text.isascii():
            return False
        if re.fullmatch(r"[\W_]+", text):
            return False
        return True
