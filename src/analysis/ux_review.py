"""Model-light UX review synthesis grounded in runtime artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urlparse

from src.agent.state import AgentState, StateSnapshot
from src.analysis.report_text import best_surface_label, clean_report_text, display_label


@dataclass
class UXSurface:
    key: str
    label: str
    url: str
    state_id: str
    title: str = ""
    page_type: str = "unknown"
    screenshot_path: str = ""
    html_path: str = ""
    actions: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

    @property
    def all_texts(self) -> list[str]:
        return [self.label, self.title, *self.actions, *self.hints, *self.prompts]


@dataclass
class UXFlowStep:
    title: str
    detail: str


@dataclass
class UXReviewFinding:
    title: str
    summary: str
    why_it_matters: str
    evidence: list[str] = field(default_factory=list)
    related_surface_keys: list[str] = field(default_factory=list)


@dataclass
class UXRecommendation:
    title: str
    action: str
    rationale: str


@dataclass
class UXVisual:
    title: str
    summary: str
    image_path: str
    html_path: str
    state_id: str
    caption: str


@dataclass
class UXReviewMemo:
    target: str
    evaluation_mode: str
    evaluation_lens: list[str]
    score: float
    overall_assessment: str
    scope_paths: list[str] = field(default_factory=list)
    scope_notes: list[str] = field(default_factory=list)
    run_evidence: list[str] = field(default_factory=list)
    flow_steps: list[UXFlowStep] = field(default_factory=list)
    strengths: list[UXReviewFinding] = field(default_factory=list)
    issues: list[UXReviewFinding] = field(default_factory=list)
    new_user_judgment: str = ""
    experienced_user_judgment: str = ""
    recommendations: list[UXRecommendation] = field(default_factory=list)
    conclusion: str = ""
    visuals: list[UXVisual] = field(default_factory=list)


class UXReviewOrchestrator:
    """Compose a reviewer-style UX memo from runtime artifacts."""

    def build(
        self,
        state: AgentState,
        page_insights: dict[str, dict] | None,
        extraction_results: dict[str, dict] | None,
        run_log_entries: list[dict] | None = None,
        coverage_data: dict[str, dict] | None = None,
        operation_trace: dict[str, Any] | None = None,
        site_hierarchy: dict[str, Any] | None = None,
    ) -> UXReviewMemo:
        page_insights = page_insights or {}
        extraction_results = extraction_results or {}
        run_log_entries = run_log_entries or []
        coverage_data = coverage_data or {}
        operation_trace = operation_trace or {}
        site_hierarchy = site_hierarchy or {}

        surfaces = self._build_surfaces(state, page_insights)
        visuals = self._visuals(surfaces)
        flow_steps = self._flow_steps(operation_trace)
        run_evidence = self._run_evidence(state, operation_trace, site_hierarchy, coverage_data)
        scope_paths = self._scope_paths(surfaces, site_hierarchy)
        scope_notes = self._scope_notes(surfaces, extraction_results, coverage_data, operation_trace)
        strengths = self._strengths(state, visuals, run_evidence, scope_paths)
        issues = self._issues(state, operation_trace, site_hierarchy, scope_paths)
        score = self._score(strengths, issues)
        recommendations = self._recommendations(issues)

        target = self._target_label(state, surfaces)
        overall_assessment = self._overall_assessment(score, strengths, issues)
        new_user_judgment = self._new_user_judgment(issues)
        experienced_user_judgment = self._experienced_user_judgment(strengths, issues)
        conclusion = self._conclusion(score, strengths, issues, scope_paths)

        return UXReviewMemo(
            target=target,
            evaluation_mode="基于真实浏览器访问、截图、DOM 快照、page insight 与运行日志的体验审查",
            evaluation_lens=["首次使用体验", "任务发起效率", "信息架构清晰度", "可理解性", "操作负担"],
            score=score,
            overall_assessment=overall_assessment,
            scope_paths=scope_paths,
            scope_notes=scope_notes,
            run_evidence=run_evidence,
            flow_steps=flow_steps,
            strengths=strengths,
            issues=issues,
            new_user_judgment=new_user_judgment,
            experienced_user_judgment=experienced_user_judgment,
            recommendations=recommendations,
            conclusion=conclusion,
            visuals=visuals,
        )

    def _build_surfaces(self, state: AgentState, page_insights: dict[str, dict]) -> list[UXSurface]:
        insights = {str(key): value for key, value in page_insights.items()}
        snapshots = sorted(state.states.values(), key=lambda item: item.timestamp)
        surfaces: list[UXSurface] = []
        for snapshot in snapshots:
            insight = insights.get(snapshot.id, {})
            surface = UXSurface(
                key=snapshot.id,
                label=self._surface_label(snapshot),
                url=snapshot.url,
                state_id=snapshot.id,
                title=clean_report_text(snapshot.title),
                page_type=self._page_type(insight),
                screenshot_path=str(snapshot.metadata.get("report_screenshot_path") or snapshot.screenshot_path),
                html_path=str(snapshot.html_path),
                actions=self._dedupe_texts(self._hint_labels(insight), limit=10),
                hints=self._dedupe_texts(self._hint_labels(insight), limit=10),
                prompts=self._dedupe_texts(self._prompt_texts(snapshot), limit=5),
            )
            surfaces.append(surface)
        return surfaces

    def _surface_label(self, snapshot: StateSnapshot) -> str:
        return clean_report_text(
            best_surface_label(
                url=snapshot.url,
                title=snapshot.title,
                capture_label=str(snapshot.metadata.get("capture_label", "") or ""),
                fallback=snapshot.title or snapshot.url,
            )
        ) or display_label(snapshot.metadata.get("capture_context", "route"))

    def _page_type(self, insight: dict[str, Any]) -> str:
        page_type = clean_report_text(str(insight.get("page_type_vision") or insight.get("page_type_dom") or ""))
        return page_type or "unknown"

    def _hint_labels(self, insight: dict[str, Any]) -> list[str]:
        labels: list[str] = []
        for item in insight.get("interaction_hints", []) or []:
            if isinstance(item, dict):
                text = clean_report_text(str(item.get("label", "")))
                if text:
                    labels.append(text)
        return labels

    def _prompt_texts(self, snapshot: StateSnapshot) -> list[str]:
        prompts: list[str] = []
        for key in ("capture_label", "capture_context"):
            text = clean_report_text(str(snapshot.metadata.get(key, "")))
            if text:
                prompts.append(text)
        return prompts

    def _target_label(self, state: AgentState, surfaces: list[UXSurface]) -> str:
        if surfaces:
            parsed = urlparse(surfaces[0].url)
            return parsed.netloc or surfaces[0].url
        if state.states:
            snapshot = next(iter(state.states.values()))
            parsed = urlparse(snapshot.url)
            return parsed.netloc or snapshot.url
        parsed = urlparse(getattr(state, "root_url", ""))
        return parsed.netloc or "unknown"

    def _scope_paths(self, surfaces: list[UXSurface], site_hierarchy: dict[str, Any]) -> list[str]:
        focus_paths = [clean_report_text(str(item)) for item in site_hierarchy.get("focus_paths", []) if clean_report_text(str(item))]
        if focus_paths:
            return focus_paths[:10]
        labels = [surface.label for surface in surfaces if surface.label]
        return self._dedupe_texts(labels, limit=10)

    def _scope_notes(
        self,
        surfaces: list[UXSurface],
        extraction_results: dict[str, dict],
        coverage_data: dict[str, dict],
        operation_trace: dict[str, Any],
    ) -> list[str]:
        notes: list[str] = []
        if surfaces:
            notes.append(f"本轮稳定落下来的代表性界面共有 `{len(surfaces)}` 个。")
        if extraction_results:
            successful = sum(1 for item in extraction_results.values() if item.get("status") == "success")
            notes.append(f"结构化抽取成功 `{successful}` 次。")
        if coverage_data:
            notes.append(f"coverage 产物中记录了 `{len(coverage_data)}` 个目标节点。")
        trace_stats = operation_trace.get("stats", {})
        if trace_stats:
            notes.append(
                f"运行过程中共发生 `{trace_stats.get('selected_targets', 0)}` 次 route 选择和 `{trace_stats.get('selected_decisions', 0)}` 次页面动作选择。"
            )
        return notes[:5]

    def _run_evidence(
        self,
        state: AgentState,
        operation_trace: dict[str, Any],
        site_hierarchy: dict[str, Any],
        coverage_data: dict[str, dict],
    ) -> list[str]:
        evidence: list[str] = []
        trace_stats = operation_trace.get("stats", {})
        if trace_stats:
            evidence.append(
                f"全程共记录 `{trace_stats.get('total_steps', 0)}` 个运行步骤，其中新 state 捕捉 `{trace_stats.get('captured_states', 0)}` 次。"
            )
        hierarchy_stats = site_hierarchy.get("stats", {})
        if hierarchy_stats:
            evidence.append(
                f"已发现节点 `{hierarchy_stats.get('total_nodes', 0)}` 个，实际访问 `{hierarchy_stats.get('visited_nodes', 0)}` 个，最大深度 `depth {hierarchy_stats.get('max_depth', 0)}`。"
            )
        if coverage_data:
            evidence.append(f"coverage 文件中保留了 `{len(coverage_data)}` 份页面覆盖记录。")
        if state.states:
            evidence.append(f"本轮共保留 `{len(state.states)}` 份可回看的 state 快照。")
        return evidence[:6]

    def _flow_steps(self, operation_trace: dict[str, Any]) -> list[UXFlowStep]:
        steps: list[UXFlowStep] = []
        for index, item in enumerate(operation_trace.get("key_steps", [])[:6], start=1):
            title = clean_report_text(str(item.get("action_label", ""))) or f"Step {index}"
            target = clean_report_text(str(item.get("target", ""))) or "当前页面"
            result = clean_report_text(str(item.get("result_label", ""))) or "未知结果"
            detail = clean_report_text(str(item.get("detail", ""))) or "无额外说明"
            steps.append(UXFlowStep(title=f"{index}. {title}", detail=f"面向 `{target}`，结果为 {result}。{detail}"))
        return steps

    def _strengths(
        self,
        state: AgentState,
        visuals: list[UXVisual],
        run_evidence: list[str],
        scope_paths: list[str],
    ) -> list[UXReviewFinding]:
        findings: list[UXReviewFinding] = []
        if run_evidence:
            findings.append(
                UXReviewFinding(
                    title="运行链路完整保留",
                    summary="这次输出不只保留了最终结论，还保留了整条访问与决策轨迹。",
                    why_it_matters="这让报告可以回溯，便于判断问题到底来自产品本身还是探索过程。",
                    evidence=run_evidence[:2],
                )
            )
        if scope_paths:
            findings.append(
                UXReviewFinding(
                    title="探索结构可读",
                    summary="已探索的网站上下级结构被整理成了可读的分支视图。",
                    why_it_matters="阅读者可以快速知道 agent 实际走到了哪里，而不是只看到孤立截图。",
                    evidence=[f"代表性分支包括：{'、'.join(f'`{item}`' for item in scope_paths[:4])}。"],
                )
            )
        if len(visuals) >= 2 or len(state.states) >= 3:
            findings.append(
                UXReviewFinding(
                    title="截图证据与 state 快照互相对应",
                    summary="报告可以把截图、DOM 快照和 state 标识对应起来。",
                    why_it_matters="这让结论不只停留在描述层，而能直接回看当时页面。",
                    evidence=[f"本轮选出了 `{len(visuals)}` 张代表性截图。"],
                )
            )
        return findings[:4]

    def _issues(
        self,
        state: AgentState,
        operation_trace: dict[str, Any],
        site_hierarchy: dict[str, Any],
        scope_paths: list[str],
    ) -> list[UXReviewFinding]:
        findings: list[UXReviewFinding] = []
        trace_stats = operation_trace.get("stats", {})
        hierarchy_stats = site_hierarchy.get("stats", {})
        captured_states = int(trace_stats.get("captured_states", len(state.states) or 0))
        max_depth = int(hierarchy_stats.get("max_depth", 0))
        no_effect = [
            item for item in operation_trace.get("steps", [])
            if str(item.get("action", "")) in {"page_action_no_effect", "page_action_skipped"}
        ]

        if captured_states < 3:
            findings.append(
                UXReviewFinding(
                    title="有效状态证据仍然偏少",
                    summary="虽然保留了完整链路，但最终沉淀为可审查 state 的页面还不够多。",
                    why_it_matters="当证据面偏窄时，报告容易过度依赖首屏，难以覆盖中层流程。",
                    evidence=[f"本轮可回看的 state 数量为 `{captured_states}`。"],
                )
            )
        if no_effect:
            findings.append(
                UXReviewFinding(
                    title="探索预算仍有一部分消耗在无效动作上",
                    summary="运行日志里仍然能看到一些没有形成新状态的动作。",
                    why_it_matters="无效动作会挤占更深层页面的预算，也会让报告证据面变窄。",
                    evidence=[f"无明显效果或被跳过的动作共 `{len(no_effect)}` 次。"],
                )
            )
        if max_depth <= 1 and scope_paths:
            findings.append(
                UXReviewFinding(
                    title="探索深度仍然偏浅",
                    summary="当前证据更像围绕入口页展开，还没有稳定深入到更多中层工作流。",
                    why_it_matters="如果深度不够，很多真正影响体验的承接与编辑流程不会进入报告。",
                    evidence=[f"当前最大探索深度为 `depth {max_depth}`。"],
                )
            )
        return findings[:4]

    def _score(self, strengths: list[UXReviewFinding], issues: list[UXReviewFinding]) -> float:
        score = 6.8 + (0.4 * len(strengths)) - (0.5 * len(issues))
        return round(max(4.8, min(score, 8.8)), 1)

    def _overall_assessment(
        self,
        score: float,
        strengths: list[UXReviewFinding],
        issues: list[UXReviewFinding],
    ) -> str:
        if score >= 7.8 and not issues:
            return "这版报告已经具备较强的证据完整性，能够直接作为 UX 评审底稿。"
        if score >= 7.0:
            return "这版报告已经接近成熟评审稿，优点是证据链完整，短板是覆盖面还可以继续扩。"
        if strengths:
            return "这版报告已经把证据链搭起来了，但还需要继续扩大 state 覆盖和中层流程证据。"
        return "当前报告仍以基础证据整理为主，还没有形成足够扎实的评审面。"

    def _new_user_judgment(self, issues: list[UXReviewFinding]) -> str:
        if any(item.title == "有效状态证据仍然偏少" for item in issues):
            return "对新用户而言，当前报告还更擅长解释入口体验，而不是完整的新手旅程。"
        return "对新用户而言，这版报告已经能较好地解释首屏到下一步之间的体验承接。"

    def _experienced_user_judgment(
        self,
        strengths: list[UXReviewFinding],
        issues: list[UXReviewFinding],
    ) -> str:
        if strengths and not issues:
            return "对熟练用户而言，这版报告已经能快速定位实际工作流中的摩擦点。"
        return "对熟练用户而言，这版报告有可回看的运行证据，但中层流程覆盖还可以继续加深。"

    def _recommendations(self, issues: list[UXReviewFinding]) -> list[UXRecommendation]:
        recommendations: list[UXRecommendation] = []
        for issue in issues:
            if issue.title == "有效状态证据仍然偏少":
                recommendations.append(
                    UXRecommendation(
                        title="继续扩展稳定 state 覆盖",
                        action="优先让 agent 更稳定地进入入口之后的一到两层页面，并确保每次成功进入后都沉淀成 state。",
                        rationale="这样可以让报告不只停留在首页或弹层，而是覆盖真正的任务承接流程。",
                    )
                )
            elif issue.title == "探索预算仍有一部分消耗在无效动作上":
                recommendations.append(
                    UXRecommendation(
                        title="压缩无效动作占比",
                        action="继续把下一步选择交给模型，并在动作无效果后更快降权或切换候选。",
                        rationale="减少预算浪费后，有限 state 更容易花在高价值路径上。",
                    )
                )
            elif issue.title == "探索深度仍然偏浅":
                recommendations.append(
                    UXRecommendation(
                        title="优先推进中层任务流",
                        action="让探索目标从首屏入口延伸到创建、编辑、导入、结果页等中层界面。",
                        rationale="这样报告才会更接近真正的产品体验评审，而不是入口观察。",
                    )
                )
        return recommendations[:4]

    def _conclusion(
        self,
        score: float,
        strengths: list[UXReviewFinding],
        issues: list[UXReviewFinding],
        scope_paths: list[str],
    ) -> str:
        strengths_text = strengths[0].title if strengths else "证据链仍在补齐"
        issues_text = issues[0].title if issues else "当前没有明显的结构性短板"
        scope_text = "、".join(f"`{item}`" for item in scope_paths[:3]) if scope_paths else "当前落下来的页面集合"
        return (
            f"综合来看，这版 UX 报告已经能围绕 {scope_text} 组织真实证据。"
            f"它当前最有价值的地方是“{strengths_text}”，下一步最值得继续推进的是“{issues_text}”。"
            f"综合评分为 `{score:.1f} / 10`。"
        )

    def _visuals(self, surfaces: list[UXSurface]) -> list[UXVisual]:
        visuals: list[UXVisual] = []
        for surface in surfaces:
            if not surface.screenshot_path:
                continue
            visuals.append(
                UXVisual(
                    title=surface.label,
                    summary=f"代表界面：{surface.label}",
                    image_path=surface.screenshot_path,
                    html_path=surface.html_path,
                    state_id=surface.state_id,
                    caption=f"该截图对应 `{surface.label}`，页面类型为 `{surface.page_type}`。",
                )
            )
            if len(visuals) >= 4:
                break
        return visuals

    def _dedupe_texts(self, items: Iterable[str], limit: int) -> list[str]:
        return _dedupe_texts(items, limit=limit)


def _dedupe_texts(items: Iterable[str], *, limit: int) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = clean_report_text(str(item or ""))
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(text)
        if len(results) >= limit:
            break
    return results