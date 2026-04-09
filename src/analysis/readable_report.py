"""Human-readable competitive-analysis report with selected screenshots."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from src.agent.state import AgentState, StateSnapshot
from src.analysis.competitive_report import CompetitiveAnalysis


class ReadableCompetitiveReportGenerator:
    """Generate a grounded, human-readable report for stakeholders."""

    MAX_VISUAL_HIGHLIGHTS = 5
    PAGE_TYPE_WEIGHTS = {
        "landing": 3.5,
        "content": 3.0,
        "docs": 3.2,
        "dashboard": 3.2,
        "list": 3.0,
        "detail": 2.8,
        "form": 2.8,
        "auth": 2.4,
        "modal": 2.2,
        "unknown": 1.0,
    }

    def generate(
        self,
        state: AgentState,
        analysis: CompetitiveAnalysis,
        page_insights: dict[str, dict] | None,
        extraction_results: dict[str, dict] | None,
        reports_dir: Path,
    ) -> str:
        """Generate a richer markdown report with contextual screenshots."""
        page_insights = page_insights or {}
        extraction_results = extraction_results or {}
        insights_by_url = self._insights_by_url(page_insights)
        extractions_by_url = self._best_extractions_by_url(extraction_results)
        highlights = self._select_visual_highlights(
            state,
            insights_by_url,
            extractions_by_url,
            reports_dir,
        )

        lines = [
            "# Competitive Analysis Report",
            "",
            "## Executive Summary",
            self._executive_summary(analysis),
            "",
            "## Product Readout",
            self._product_readout(analysis),
            "",
            "## Key Findings",
        ]

        findings = self._key_findings(analysis)
        if findings:
            lines.extend(f"- {item}" for item in findings)
        else:
            lines.append("- The current run produced limited confident findings; a larger budget is recommended.")

        lines.extend(["", "## Visual Walkthrough"])
        if highlights:
            for highlight in highlights:
                lines.extend([
                    "",
                    f"### {highlight['title']}",
                    highlight["summary"],
                    "",
                    f"![{highlight['title']}]({highlight['image_path']})",
                    "",
                    f"*Why this matters:* {highlight['caption']}",
                ])
        else:
            lines.append("")
            lines.append("No screenshot highlights were selected from the current run.")

        lines.extend(["", "## Modules And Workflows"])
        module_lines = self._module_lines(analysis)
        if module_lines:
            lines.extend(f"- {item}" for item in module_lines)
        else:
            lines.append("- No stable module breakdown was inferred from the current evidence.")

        lines.extend(["", "## Risks And Follow-Up"])
        followups = self._followup_lines(analysis)
        if followups:
            lines.extend(f"- {item}" for item in followups)
        else:
            lines.append("- Expand the crawl budget and compare against a second benchmark site.")

        lines.extend([
            "",
            "## Method Notes",
            self._method_notes(analysis),
        ])
        return "\n".join(lines).strip() + "\n"

    def _executive_summary(self, analysis: CompetitiveAnalysis) -> str:
        summary = analysis.competitive_summary
        page_mix = self._format_page_mix(analysis.page_type_distribution)
        states = int(analysis.run_metadata.get("states_captured", 0))
        routes = int(analysis.run_metadata.get("visited_routes", 0))
        budget = int(analysis.run_metadata.get("budget_used", 0))
        category = self._display_label(summary.product_category_guess)
        return (
            f"This run suggests **{analysis.target}** is primarily a **{category}** surface. "
            f"The captured evidence leans toward {page_mix}. "
            f"The agent captured {states} states across {routes} visited routes, "
            f"using {budget} budgeted captures."
        )

    def _product_readout(self, analysis: CompetitiveAnalysis) -> str:
        summary = analysis.competitive_summary
        modules = ", ".join(
            module.get("name", "unknown")
            for module in analysis.feature_modules[:4]
            if module.get("name")
        )
        modules_text = modules if modules else "no stable module grouping yet"
        return (
            f"The strongest evidence points to {modules_text}. "
            f"Application surface score is **{summary.application_surface_score:.2f}**, "
            f"data density score is **{summary.data_density_score:.2f}**, "
            f"and workflow complexity is **{summary.workflow_complexity_score:.2f}**. "
            "These scores should be read as comparative hints rather than absolute product grades."
        )

    def _key_findings(self, analysis: CompetitiveAnalysis) -> list[str]:
        findings: list[str] = []
        findings.extend(analysis.competitive_summary.observed_strengths[:3])
        findings.extend(analysis.competitive_summary.key_differentiators[:2])
        findings.extend(analysis.competitive_summary.observed_gaps[:2])
        deduped: list[str] = []
        seen: set[str] = set()
        for item in findings:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    def _module_lines(self, analysis: CompetitiveAnalysis) -> list[str]:
        lines: list[str] = []
        for module in analysis.feature_modules[:6]:
            name = str(module.get("name", "unknown"))
            evidence_count = int(module.get("evidence_count", 0))
            lines.append(f"Module `{name}` appeared in {evidence_count} captured surface(s).")

        if analysis.interaction_patterns:
            patterns = ", ".join(
                f"{item.get('name', 'unknown')} ({item.get('count', 0)})"
                for item in analysis.interaction_patterns[:5]
            )
            lines.append(f"Observed interaction patterns: {patterns}.")

        if analysis.data_entities:
            entities = ", ".join(entity.get("name", "unknown") for entity in analysis.data_entities[:6])
            lines.append(f"Representative extracted entities or section titles: {entities}.")

        return lines

    def _followup_lines(self, analysis: CompetitiveAnalysis) -> list[str]:
        lines = list(analysis.competitive_summary.observed_gaps[:3])
        lines.extend(analysis.comparison_notes[:2])
        if not lines:
            lines.append(
                "Run a larger-budget pass and compare this target against one or two direct peers."
            )
        return lines

    def _method_notes(self, analysis: CompetitiveAnalysis) -> str:
        total_targets = int(analysis.run_metadata.get("total_targets", 0))
        states = int(analysis.run_metadata.get("states_captured", 0))
        budget = int(analysis.run_metadata.get("budget_used", 0))
        depth_max = int(analysis.site_structure_summary.get("depth_max", 0))
        return (
            f"This report is grounded in deterministic browser captures, DOM snapshots, and structured evidence. "
            f"The run discovered {total_targets} targets, captured {states} states, "
            f"used {budget} budgeted captures, and reached depth {depth_max}. "
            "The screenshot walkthrough favors surfaces with higher novelty, stronger evidence density, "
            "better page-type diversity, and viewport-focused images except where a full-page view is more justified."
        )

    def _insights_by_url(self, page_insights: dict[str, dict]) -> dict[str, dict]:
        deduped: dict[str, dict] = {}
        for insight in page_insights.values():
            url = str(insight.get("url", "")).strip()
            if not url:
                continue
            existing = deduped.get(url)
            if existing is None:
                deduped[url] = insight
                continue
            existing_id = str(existing.get("state_id", ""))
            candidate_id = str(insight.get("state_id", ""))
            if existing_id.startswith("observe_") and not candidate_id.startswith("observe_"):
                deduped[url] = insight
        return deduped

    def _best_extractions_by_url(self, extraction_results: dict[str, dict]) -> dict[str, dict]:
        ranked: dict[str, dict] = {}
        for result in extraction_results.values():
            url = str(result.get("url", "")).strip()
            if not url:
                continue
            current = ranked.get(url)
            if current is None or self._extraction_rank(result) > self._extraction_rank(current):
                ranked[url] = result
        return ranked

    def _extraction_rank(self, result: dict) -> tuple[int, int, int]:
        status = str(result.get("status", ""))
        success_rank = 2 if status == "success" else 1 if status == "empty" else 0
        summary = result.get("summary", {}) or {}
        evidence_count = int(summary.get("evidence_unit_count", 0) or len(result.get("evidence_units", [])))
        section_count = int(summary.get("content_section_count", 0))
        return success_rank, evidence_count, section_count

    def _select_visual_highlights(
        self,
        state: AgentState,
        insights_by_url: dict[str, dict],
        extractions_by_url: dict[str, dict],
        reports_dir: Path,
    ) -> list[dict[str, str]]:
        candidates: list[dict[str, object]] = []

        for snapshot in sorted(state.states.values(), key=lambda item: item.timestamp):
            image_source = str(snapshot.metadata.get("report_screenshot_path") or snapshot.screenshot_path)
            screenshot_path = Path(image_source)
            if not snapshot.screenshot_path or not screenshot_path.exists():
                continue

            insight = insights_by_url.get(snapshot.url, {})
            extraction = extractions_by_url.get(snapshot.url, {})
            page_type = self._page_type(insight, extraction)
            score = self._visual_score(snapshot, insight, extraction, page_type)
            title = self._visual_title(state, snapshot, page_type)
            candidates.append({
                "url": snapshot.url,
                "page_type": page_type,
                "score": score,
                "title": title,
                "summary": self._visual_summary(snapshot, extraction, page_type),
                "caption": self._visual_caption(snapshot, extraction, page_type),
                "image_path": self._relative_path(screenshot_path, reports_dir),
            })

        if not candidates:
            return []

        ordered = sorted(candidates, key=lambda item: (-float(item["score"]), str(item["title"])))
        selected: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        seen_page_types: set[str] = set()

        for candidate in ordered:
            url = str(candidate["url"])
            page_type = str(candidate["page_type"])
            if url in seen_urls or page_type in seen_page_types:
                continue
            selected.append(self._stringify_candidate(candidate))
            seen_urls.add(url)
            seen_page_types.add(page_type)
            if len(selected) >= self.MAX_VISUAL_HIGHLIGHTS:
                return selected

        for candidate in ordered:
            url = str(candidate["url"])
            if url in seen_urls:
                continue
            selected.append(self._stringify_candidate(candidate))
            seen_urls.add(url)
            if len(selected) >= self.MAX_VISUAL_HIGHLIGHTS:
                break

        return selected

    def _stringify_candidate(self, candidate: dict[str, object]) -> dict[str, str]:
        return {key: str(value) for key, value in candidate.items() if key != "score"}

    def _visual_score(
        self,
        snapshot: StateSnapshot,
        insight: dict,
        extraction: dict,
        page_type: str,
    ) -> float:
        score = float(snapshot.novelty_score) * 5
        score += self.PAGE_TYPE_WEIGHTS.get(page_type, 1.0)
        if snapshot.depth == 0:
            score += 2.5
        if insight.get("high_value_page"):
            score += 2.5

        target_context = str(snapshot.metadata.get("capture_context", "route"))
        if target_context == "route":
            score += 1.5
        elif target_context in {"open_modal", "switch_tab", "click_action"}:
            score += 0.8

        if extraction:
            if extraction.get("status") == "success":
                score += 2.0
            summary = extraction.get("summary", {}) or {}
            score += min(int(summary.get("evidence_unit_count", 0)), 20) / 5
            score += min(int(summary.get("content_section_count", 0)), 10) / 4
        return round(score, 2)

    def _visual_title(self, state: AgentState, snapshot: StateSnapshot, page_type: str) -> str:
        target = state.targets.get(snapshot.target_id)
        label = str(snapshot.metadata.get("capture_label", "")).strip()
        if not label and target:
            label = target.label
        if not label:
            label = self._display_label(page_type)
        if label == "root":
            domain = urlparse(snapshot.url).netloc or "homepage"
            return f"{domain} home"
        return label

    def _visual_summary(self, snapshot: StateSnapshot, extraction: dict, page_type: str) -> str:
        evidence_text = self._evidence_text(extraction)
        return (
            f"This capture represents a **{self._display_label(page_type)}** surface "
            f"with novelty score **{snapshot.novelty_score:.2f}**. {evidence_text}"
        )

    def _visual_caption(self, snapshot: StateSnapshot, extraction: dict, page_type: str) -> str:
        highlights = self._notable_items(extraction)
        if highlights:
            return (
                f"Selected as a strong {self._display_label(page_type)} example. "
                f"Notable evidence includes {highlights}."
            )
        return (
            f"Selected to preserve a visually representative {self._display_label(page_type)} surface "
            "for later comparison."
        )

    def _page_type(self, insight: dict, extraction: dict) -> str:
        page_type_vision = str(insight.get("page_type_vision", "")).strip()
        if page_type_vision and page_type_vision != "unknown":
            return page_type_vision
        page_type_dom = str(insight.get("page_type_dom", "")).strip()
        if page_type_dom:
            return page_type_dom
        extraction_type = str(extraction.get("page_type", "")).strip()
        return extraction_type or "unknown"

    def _evidence_text(self, extraction: dict) -> str:
        if not extraction:
            return "Evidence density is still limited on this page."
        summary = extraction.get("summary", {}) or {}
        parts: list[str] = []
        hero_count = int(summary.get("hero_title_count", 0))
        cta_count = int(summary.get("primary_cta_count", 0))
        section_count = int(summary.get("content_section_count", 0))
        nav_count = int(summary.get("nav_item_count", 0))
        field_count = len(extraction.get("fields", []))
        if hero_count:
            parts.append(f"{hero_count} hero title(s)")
        if cta_count:
            parts.append(f"{cta_count} CTA(s)")
        if section_count:
            parts.append(f"{section_count} content section(s)")
        if nav_count:
            parts.append(f"{nav_count} navigation item(s)")
        if field_count:
            parts.append(f"{field_count} field(s)")
        if not parts:
            return "Evidence density is still limited on this page."
        return "Captured evidence includes " + ", ".join(parts) + "."

    def _notable_items(self, extraction: dict) -> str:
        items: list[str] = []
        for unit in extraction.get("evidence_units", [])[:12]:
            text = str(unit.get("normalized_text") or unit.get("raw_text") or "").strip()
            kind = str(unit.get("kind", "")).strip()
            if not text or kind not in {"hero", "cta", "content_section"}:
                continue
            items.append(f"`{text}`")
            if len(items) >= 3:
                break
        if items:
            if len(items) == 1:
                return items[0]
            return ", ".join(items[:-1]) + f", and {items[-1]}"
        return ""

    def _format_page_mix(self, page_type_distribution: dict[str, int]) -> str:
        if not page_type_distribution:
            return "an uncertain page mix"
        ranked = sorted(page_type_distribution.items(), key=lambda item: (-item[1], item[0]))[:3]
        labels = [f"{self._display_label(name)} ({count})" for name, count in ranked]
        if len(labels) == 1:
            return labels[0]
        return ", ".join(labels[:-1]) + f", and {labels[-1]}"

    def _relative_path(self, path: Path, reports_dir: Path) -> str:
        return os.path.relpath(path, reports_dir).replace("\\", "/")

    def _display_label(self, value: str) -> str:
        return value.replace("_", " ").strip() if value else "unknown"
