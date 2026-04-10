"""Reviewer-style UX report renderer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.agent.state import AgentState
from src.analysis.ux_review import UXFlowStep, UXReviewFinding, UXReviewMemo, UXReviewOrchestrator


class UserExperienceReportGenerator:
    """Generate a richer UX review markdown report from captured artifacts."""

    def __init__(self) -> None:
        self.orchestrator = UXReviewOrchestrator()

    def generate(
        self,
        state: AgentState,
        page_insights: dict[str, dict] | None,
        extraction_results: dict[str, dict] | None,
        reports_dir: Path,
        *,
        run_log_entries: list[dict] | None = None,
        coverage_data: dict[str, dict] | None = None,
        operation_trace: dict[str, Any] | None = None,
        site_hierarchy: dict[str, Any] | None = None,
    ) -> str:
        memo = self.orchestrator.build(
            state,
            page_insights,
            extraction_results,
            run_log_entries=run_log_entries,
            coverage_data=coverage_data,
            operation_trace=operation_trace,
            site_hierarchy=site_hierarchy,
        )
        artifacts_dir = reports_dir.parent / "artifacts"

        lines = [
            f"# {self._title(memo.target)}用户体验报告",
            "",
            "## 概览",
            f"- 评估对象：`https://{memo.target}`",
            f"- 评估方式：{memo.evaluation_mode}",
            f"- 评估视角：{'、'.join(memo.evaluation_lens)}",
            f"- 综合评价：{memo.overall_assessment}",
            "",
            self._overview_paragraph(memo),
            "",
            "## 本次探索范围",
            "",
            "本次实际探索了以下界面或支线：",
        ]

        if memo.scope_paths:
            lines.extend([f"- `{path}`" for path in memo.scope_paths])
        else:
            lines.append("- 本轮没有稳定沉淀出可审查界面。")

        if memo.scope_notes:
            lines.extend(["", *[f"- {note}" for note in memo.scope_notes]])

        lines.extend(["", "## 运行证据"])
        lines.extend([f"- {item}" for item in memo.run_evidence] or ["- 当前没有足够运行证据。"])
        lines.extend(
            [
                f"- 关键 artifact：[run_log.jsonl]({self._relative_path(artifacts_dir / 'run_log.jsonl', reports_dir)})、"
                f"[inventory.json]({self._relative_path(artifacts_dir / 'inventory.json', reports_dir)})、"
                f"[coverage.json]({self._relative_path(artifacts_dir / 'coverage.json', reports_dir)})",
                f"- 运行链路 artifact：[operation_trace.md]({self._relative_path(reports_dir / 'operation_trace.md', reports_dir)})、"
                f"[operation_trace.json]({self._relative_path(artifacts_dir / 'operation_trace.json', reports_dir)})",
                f"- 结构树 artifact：[site_hierarchy.md]({self._relative_path(reports_dir / 'site_hierarchy.md', reports_dir)})、"
                f"[site_hierarchy.json]({self._relative_path(artifacts_dir / 'site_hierarchy.json', reports_dir)})、"
                f"[sitemap.json]({self._relative_path(artifacts_dir / 'sitemap.json', reports_dir)})",
            ]
        )

        lines.extend(["", "## Agent 访问链路"])
        if memo.flow_steps:
            lines.extend(self._flow_sections(memo.flow_steps))
        else:
            lines.append("本轮没有足够的运行日志用于重建访问链路。")

        lines.extend(["", "## 已探索站点结构"])
        lines.extend(self._site_hierarchy_section(site_hierarchy))

        lines.extend(["", "## 全程操作记录"])
        lines.extend(self._operation_trace_section(operation_trace))

        lines.extend(["", "## 主要优点"])
        if memo.strengths:
            lines.extend(self._finding_sections(memo.strengths))
        else:
            lines.append("当前证据还不足以稳定提炼出明确优点。")

        lines.extend(["", "## 主要问题"])
        if memo.issues:
            lines.extend(self._finding_sections(memo.issues))
        else:
            lines.append("当前证据还不足以稳定提炼出明确问题。")

        lines.extend(["", "## 截图与 Artifact"])
        if memo.visuals:
            for item in memo.visuals:
                image_path = self._relative_path(Path(item.image_path), reports_dir)
                html_path = self._relative_path(Path(item.html_path), reports_dir)
                insight_path = self._relative_path(artifacts_dir / "page_insights" / f"{item.state_id}_insight.json", reports_dir)
                lines.extend(
                    [
                        "",
                        f"### {item.title}",
                        item.summary,
                        "",
                        f"![{item.title}]({image_path})",
                        "",
                        f"- 截图：`{image_path}`",
                        f"- DOM 快照：`{html_path}`",
                        f"- Page insight：`{insight_path}`",
                        f"- 说明：{item.caption}",
                    ]
                )
        else:
            lines.append("本轮没有选出适合写入报告的截图。")

        lines.extend(
            [
                "",
                "## 用户体验判断",
                "### 对新用户",
                memo.new_user_judgment or "当前证据不足以稳定判断新用户的启动体验。",
                "",
                "### 对熟练用户",
                memo.experienced_user_judgment or "当前证据不足以稳定判断熟练用户的效率体验。",
            ]
        )

        lines.extend(["", "## 优先级最高的改进建议"])
        if memo.recommendations:
            for index, item in enumerate(memo.recommendations, start=1):
                lines.extend(
                    [
                        "",
                        f"### {index}. {item.title}",
                        item.action,
                        "",
                        f"优先级原因：{item.rationale}",
                    ]
                )
        else:
            lines.append("建议先补一轮更深的任务流证据，再做更强的改版判断。")

        lines.extend(["", "## 结论", memo.conclusion])
        return "\n".join(lines).strip() + "\n"

    def _title(self, target: str) -> str:
        host = target.split(":", 1)[0]
        brand = host.split(".", 1)[0]
        return f"{brand.capitalize()} " if brand else ""

    def _overview_paragraph(self, memo: UXReviewMemo) -> str:
        top_strength = memo.strengths[0].title if memo.strengths else "暂时没有稳定提炼出的优点"
        top_issue = memo.issues[0].title if memo.issues else "暂时没有稳定提炼出的问题"
        return f"整体来看，这轮证据说明产品方向是成立的。最明确的正向信号是“{top_strength}”，最影响首次进入体验的拖累点则是“{top_issue}”。"

    def _flow_sections(self, steps: list[UXFlowStep]) -> list[str]:
        lines: list[str] = []
        for index, item in enumerate(steps, start=1):
            lines.extend(["", f"### {index}. {item.title}", item.detail])
        return lines

    def _finding_sections(self, findings: list[UXReviewFinding]) -> list[str]:
        lines: list[str] = []
        for index, item in enumerate(findings, start=1):
            lines.extend(
                [
                    "",
                    f"### {index}. {item.title}",
                    item.summary,
                    "",
                    f"为什么重要：{item.why_it_matters}",
                ]
            )
            if item.evidence:
                lines.extend(["", "证据：", *[f"- {evidence}" for evidence in item.evidence]])
        return lines

    def _site_hierarchy_section(self, site_hierarchy: dict[str, Any] | None) -> list[str]:
        if not site_hierarchy:
            return ["本轮没有额外生成站点结构树。"]

        stats = site_hierarchy.get("stats", {})
        focus_paths = site_hierarchy.get("focus_paths", [])
        tree_lines = site_hierarchy.get("tree_lines", [])
        lines = [
            f"- 已发现 `{stats.get('total_nodes', 0)}` 个节点，其中 `{stats.get('visited_nodes', 0)}` 个形成了实际访问证据。",
            f"- 结构最深探索到 `depth {stats.get('max_depth', 0)}`。",
        ]
        if focus_paths:
            lines.append(f"- 本轮真正走到的代表性链路包括：{self._quoted_list(focus_paths[:6])}。")
        if tree_lines:
            lines.extend(["", "```text", *tree_lines[:24], "```"])
        return lines

    def _operation_trace_section(self, operation_trace: dict[str, Any] | None) -> list[str]:
        if not operation_trace:
            return ["本轮没有额外生成操作记录摘要。"]

        stats = operation_trace.get("stats", {})
        key_steps = operation_trace.get("key_steps", [])
        lines = [
            f"- 全程共记录 `{stats.get('total_steps', 0)}` 个运行步骤，成功 / 失败 / 跳过分别为 `{stats.get('successful_steps', 0)} / {stats.get('failed_steps', 0)} / {stats.get('skipped_steps', 0)}`。",
            f"- 其中有 `{stats.get('selected_targets', 0)}` 次 route 选择、`{stats.get('selected_decisions', 0)}` 次页面动作选择、`{stats.get('captured_states', 0)}` 次新 state 捕获。",
        ]
        if key_steps:
            lines.append("")
            for step in key_steps[:10]:
                target = step.get("target") or "-"
                detail = step.get("detail") or "-"
                lines.append(
                    f"- Step {step.get('step')}: {step.get('action_label')} -> `{target}`，结果：{step.get('result_label')}；{detail}"
                )
        return lines

    def _quoted_list(self, items: list[str]) -> str:
        return "、".join(f"`{item}`" for item in items if item)

    def _relative_path(self, path: Path, reports_dir: Path) -> str:
        return os.path.relpath(path, reports_dir).replace("\\", "/")
