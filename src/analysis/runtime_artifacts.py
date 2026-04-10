"""Helpers for richer runtime artifacts used by UX reports."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from src.agent.state import AgentState, ExplorationTarget, StateSnapshot
from src.analysis.report_text import best_surface_label, clean_report_text, display_label


def build_operation_trace(run_log_entries: list[dict] | None) -> dict[str, Any]:
    """Normalize JSONL run-log rows into a report-friendly trace object."""
    rows = sorted(run_log_entries or [], key=lambda item: int(item.get("step", 0)))
    phase_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    result_counts: Counter[str] = Counter()
    steps: list[dict[str, Any]] = []

    for row in rows:
        phase = clean_report_text(str(row.get("phase", ""))) or "unknown"
        action = clean_report_text(str(row.get("action", ""))) or "unknown"
        result = clean_report_text(str(row.get("result", ""))) or "unknown"
        target = _pretty_trace_target(str(row.get("target", "")))
        reason = clean_report_text(str(row.get("reason", "")))
        duration_ms = int(row.get("duration_ms", 0) or 0)

        phase_counts[phase] += 1
        action_counts[action] += 1
        result_counts[result] += 1
        steps.append(
            {
                "step": int(row.get("step", 0) or 0),
                "timestamp": str(row.get("timestamp", "")),
                "phase": phase,
                "phase_label": display_label(phase),
                "action": action,
                "action_label": _action_label(action),
                "target": target,
                "result": result,
                "result_label": _result_label(result),
                "detail": reason,
                "duration_ms": duration_ms,
            }
        )

    total_duration_ms = sum(item["duration_ms"] for item in steps)
    return {
        "stats": {
            "total_steps": len(steps),
            "total_duration_ms": total_duration_ms,
            "successful_steps": result_counts.get("success", 0),
            "failed_steps": result_counts.get("failed", 0),
            "skipped_steps": result_counts.get("skipped", 0),
            "selected_targets": action_counts.get("selected_target", 0),
            "selected_decisions": action_counts.get("selected_decision", 0),
            "captured_states": sum(
                1
                for item in steps
                if item["action"].startswith("capture_") and item["result"] == "success"
            ),
            "phase_counts": dict(phase_counts),
            "action_counts": dict(action_counts),
        },
        "steps": steps,
        "key_steps": _key_trace_steps(steps),
    }


def render_operation_trace_markdown(operation_trace: dict[str, Any]) -> str:
    """Render a human-readable operation trace markdown artifact."""
    stats = operation_trace.get("stats", {})
    steps = operation_trace.get("steps", [])

    lines = [
        "# 全程操作记录",
        "",
        "## 概览",
        f"- 总步骤数：`{stats.get('total_steps', 0)}`",
        f"- 成功 / 失败 / 跳过：`{stats.get('successful_steps', 0)} / {stats.get('failed_steps', 0)} / {stats.get('skipped_steps', 0)}`",
        f"- route 选择：`{stats.get('selected_targets', 0)}` 次",
        f"- 页面动作选择：`{stats.get('selected_decisions', 0)}` 次",
        f"- 形成新 state 的动作：`{stats.get('captured_states', 0)}` 次",
        "",
        "## 逐步记录",
        "",
        "| Step | Phase | Action | Target | Result | Detail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for step in steps:
        detail = str(step.get("detail", "")).replace("\n", " ").replace("|", "/")
        target = str(step.get("target", "")).replace("|", "/")
        lines.append(
            f"| {step.get('step', '')} | {step.get('phase_label', '')} | {step.get('action_label', '')} | {target or '-'} | {step.get('result_label', '')} | {detail or '-'} |"
        )

    return "\n".join(lines).strip() + "\n"


def build_site_hierarchy(state: AgentState) -> dict[str, Any]:
    """Build explored-site hierarchy directly from discovered targets."""
    snapshots_by_target = _latest_snapshots_by_target(state)
    children: dict[str | None, list[str]] = defaultdict(list)
    nodes: dict[str, dict[str, Any]] = {}

    for target in state.targets.values():
        children[target.parent_id].append(target.id)

    for target in state.targets.values():
        snapshot = snapshots_by_target.get(target.id)
        locator = target.locator if target.locator.startswith(("http://", "https://")) else ""
        url = snapshot.url if snapshot else locator
        label = _pretty_target_label(target, snapshot)
        nodes[target.id] = {
            "id": target.id,
            "label": label,
            "type": target.target_type.value,
            "depth": target.depth,
            "parent_id": target.parent_id,
            "discovery_method": target.discovery_method,
            "visited": target.id in state.visited,
            "skipped": target.id in state.skipped,
            "locator": target.locator,
            "url": url,
            "url_path": _short_path(url),
            "state_id": snapshot.id if snapshot else "",
            "children": [],
        }

    for parent_id, child_ids in children.items():
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"] = child_ids

    root_ids = sorted(children.get(None, []), key=lambda item: _node_sort_key(nodes[item]))
    tree_lines: list[str] = []
    for root_id in root_ids:
        _append_tree_lines(root_id, nodes, children, tree_lines, "")

    focus_paths = _focus_paths(root_ids, nodes, children)
    visited_labels = [nodes[node_id]["label"] for node_id in nodes if nodes[node_id]["visited"]]

    return {
        "stats": {
            "total_nodes": len(nodes),
            "visited_nodes": sum(1 for node in nodes.values() if node["visited"]),
            "skipped_nodes": sum(1 for node in nodes.values() if node["skipped"]),
            "route_nodes": sum(1 for node in nodes.values() if node["type"] == "route"),
            "interaction_nodes": sum(1 for node in nodes.values() if node["type"] != "route"),
            "max_depth": max((int(node["depth"]) for node in nodes.values()), default=0),
        },
        "nodes": [nodes[node_id] for node_id in sorted(nodes, key=lambda item: _node_sort_key(nodes[item]))],
        "tree_lines": tree_lines,
        "focus_paths": focus_paths,
        "visited_labels": visited_labels[:12],
    }


def render_site_hierarchy_markdown(site_hierarchy: dict[str, Any]) -> str:
    """Render a human-readable site hierarchy artifact."""
    stats = site_hierarchy.get("stats", {})
    tree_lines = site_hierarchy.get("tree_lines", [])
    focus_paths = site_hierarchy.get("focus_paths", [])

    lines = [
        "# 已探索网站结构",
        "",
        "## 概览",
        f"- 已发现节点：`{stats.get('total_nodes', 0)}`",
        f"- 实际访问节点：`{stats.get('visited_nodes', 0)}`",
        f"- 最大探索深度：`{stats.get('max_depth', 0)}`",
        "",
    ]

    if focus_paths:
        lines.extend(["## 重点分支", *[f"- {path}" for path in focus_paths[:12]], ""])

    lines.extend(["## 结构树", "", "```text", *tree_lines[:200], "```"])
    return "\n".join(lines).strip() + "\n"


def _key_trace_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    key_actions = {
        "login",
        "selected_target",
        "selected_decision",
        "navigate",
        "reobserve_state",
        "capture_route",
        "capture_workspace_navigation",
        "page_action_no_effect",
        "page_action_skipped",
        "frontier_empty",
        "budget_exhausted",
    }
    selected = [step for step in steps if str(step.get("action", "")) in key_actions]
    return selected[:40]


def _pretty_trace_target(raw_target: str) -> str:
    target = clean_report_text(raw_target)
    if not target:
        return ""
    if target.startswith(("http://", "https://")):
        return best_surface_label(url=target, fallback=target)
    return target


def _latest_snapshots_by_target(state: AgentState) -> dict[str, StateSnapshot]:
    latest: dict[str, StateSnapshot] = {}
    snapshots = sorted(state.states.values(), key=lambda item: item.timestamp)
    for snapshot in snapshots:
        latest[snapshot.target_id] = snapshot
    return latest


def _pretty_target_label(target: ExplorationTarget, snapshot: StateSnapshot | None) -> str:
    if snapshot:
        label = best_surface_label(
            url=snapshot.url,
            title=snapshot.title,
            capture_label=str(snapshot.metadata.get("capture_label", "") or target.label),
            fallback=target.label or snapshot.url,
        )
        if label:
            return _normalize_visible_label(label)
    if target.locator.startswith(("http://", "https://")):
        return _normalize_visible_label(
            best_surface_label(url=target.locator, capture_label=target.label, fallback=target.label or target.locator)
        )
    return _normalize_visible_label(clean_report_text(target.label) or display_label(target.target_type.value))


def _node_sort_key(node: dict[str, Any]) -> tuple[int, str]:
    return (int(node.get("depth", 0)), str(node.get("label", "")).lower())


def _short_path(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return path


def _append_tree_lines(
    node_id: str,
    nodes: dict[str, dict[str, Any]],
    children: dict[str | None, list[str]],
    lines: list[str],
    prefix: str,
) -> None:
    node = nodes[node_id]
    status = "visited" if node.get("visited") else "discovered"
    suffix = f" ({status}, {node.get('type')}, depth {node.get('depth')})"
    if node.get("url_path"):
        suffix += f" -> {node['url_path']}"
    lines.append(f"{prefix}{node['label']}{suffix}")
    child_ids = sorted(children.get(node_id, []), key=lambda item: _node_sort_key(nodes[item]))
    for child_id in child_ids:
        _append_tree_lines(child_id, nodes, children, lines, prefix + "  ")


def _focus_paths(
    root_ids: list[str],
    nodes: dict[str, dict[str, Any]],
    children: dict[str | None, list[str]],
) -> list[str]:
    results: list[tuple[int, str]] = []

    def walk(node_id: str, path: list[str]) -> None:
        node = nodes[node_id]
        next_path = path + [node["label"]]
        child_ids = sorted(children.get(node_id, []), key=lambda item: _node_sort_key(nodes[item]))
        visited_children = [child_id for child_id in child_ids if nodes[child_id]["visited"]]
        if node["visited"] and not visited_children:
            results.append((len(next_path), " > ".join(next_path)))
            return
        for child_id in visited_children:
            walk(child_id, next_path)

    for root_id in root_ids:
        walk(root_id, [])

    seen: set[str] = set()
    deduped: list[str] = []
    for _, item in sorted(results, key=lambda pair: (-pair[0], pair[1].lower())):
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped[:16]


def _normalize_visible_label(value: str) -> str:
    text = clean_report_text(value)
    if not text:
        return ""
    text = re.sub(r"^[^\w\u4e00-\u9fff]+", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _action_label(action: str) -> str:
    mapping = {
        "launch_browser": "启动浏览器",
        "login": "执行登录",
        "extract_candidates": "观察候选入口",
        "selected_target": "选择路由",
        "selected_decision": "选择页面动作",
        "navigate": "跳转路由",
        "reobserve_state": "状态变化后重观察",
        "capture_route": "捕捉路由 state",
        "capture_workspace_navigation": "捕捉页面动作 state",
        "page_action_no_effect": "动作无明显变化",
        "page_action_skipped": "动作跳过",
        "skip_interaction": "因低新颖度跳过",
        "analyze_page": "分析页面",
        "frontier_empty": "前沿耗尽",
        "budget_exhausted": "预算耗尽",
        "generate_inventory": "生成 inventory",
        "generate_sitemap": "生成 sitemap",
        "generate_coverage": "生成 coverage",
        "generate_site_memory": "生成 site memory",
        "generate_extraction_artifacts": "生成抽取产物",
        "generate_report": "生成探索报告",
        "generate_ux_report": "生成 UX 报告",
    }
    if action in mapping:
        return mapping[action]
    return display_label(action)


def _result_label(result: str) -> str:
    mapping = {
        "success": "成功",
        "failed": "失败",
        "skipped": "跳过",
        "retry": "重试",
    }
    return mapping.get(result, display_label(result))