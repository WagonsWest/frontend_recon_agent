"""Cross-site comparison report generation for batch runs."""

from __future__ import annotations

from typing import Any


class ComparisonReportGenerator:
    """Generate a compact comparison view across multiple site analyses."""

    def generate_markdown(self, sites: list[dict[str, Any]]) -> str:
        lines = [
            "# Comparison Report",
            "",
            "## Compared Sites",
        ]

        for site in sites:
            lines.append(
                f"- **{site['name']}**: {site['target']} "
                f"(report: `{site['readable_report_path']}`)"
            )

        lines.extend(["", "## Score Overview"])
        for site in sites:
            summary = site.get("summary", {})
            lines.append(
                f"- **{site['name']}**: application {summary.get('application_surface_score', 0):.2f}, "
                f"data density {summary.get('data_density_score', 0):.2f}, "
                f"workflow complexity {summary.get('workflow_complexity_score', 0):.2f}"
            )

        lines.extend(["", "## Product Category Guess"])
        for site in sites:
            lines.append(
                f"- **{site['name']}**: {site.get('product_category_guess', 'unknown')}"
            )

        lines.extend(["", "## Page Type Mix"])
        for site in sites:
            page_mix = self._format_page_mix(site.get("page_type_distribution", {}))
            lines.append(f"- **{site['name']}**: {page_mix}")

        lines.extend(["", "## Notable Modules"])
        for site in sites:
            modules = ", ".join(site.get("modules", [])[:6]) or "none"
            lines.append(f"- **{site['name']}**: {modules}")

        lines.extend(["", "## Strengths And Gaps"])
        for site in sites:
            lines.append(f"### {site['name']}")
            strengths = site.get("strengths", [])
            gaps = site.get("gaps", [])
            if strengths:
                lines.append("Strengths:")
                lines.extend(f"- {item}" for item in strengths[:3])
            else:
                lines.append("Strengths:")
                lines.append("- No high-confidence strengths were extracted.")
            if gaps:
                lines.append("Gaps:")
                lines.extend(f"- {item}" for item in gaps[:3])
            else:
                lines.append("Gaps:")
                lines.append("- No major gaps were highlighted in the current run.")
            lines.append("")

        lines.extend(["## Comparison Notes"])
        lines.extend(f"- {item}" for item in self._comparison_notes(sites))
        return "\n".join(lines).strip() + "\n"

    def _format_page_mix(self, distribution: dict[str, int]) -> str:
        if not distribution:
            return "unknown"
        ranked = sorted(distribution.items(), key=lambda item: (-item[1], item[0]))[:4]
        return ", ".join(f"{name} ({count})" for name, count in ranked)

    def _comparison_notes(self, sites: list[dict[str, Any]]) -> list[str]:
        if len(sites) < 2:
            return ["Only one site was available, so no pairwise comparison was generated."]

        notes: list[str] = []
        categories = {site["name"]: site.get("product_category_guess", "unknown") for site in sites}
        if len(set(categories.values())) > 1:
            notes.append(
                "The compared sites do not cluster into the same top-level product category, "
                "so the outputs should be read as adjacent-surface comparison rather than direct peers."
            )
        else:
            notes.append(
                f"The compared sites cluster around `{next(iter(categories.values()))}`, "
                "which makes the score and module comparison more directly meaningful."
            )

        highest_data_density = max(sites, key=lambda item: item["summary"].get("data_density_score", 0))
        notes.append(
            f"`{highest_data_density['name']}` showed the strongest data density signal in this batch."
        )

        highest_workflow = max(sites, key=lambda item: item["summary"].get("workflow_complexity_score", 0))
        notes.append(
            f"`{highest_workflow['name']}` showed the strongest workflow complexity signal in this batch."
        )
        return notes
