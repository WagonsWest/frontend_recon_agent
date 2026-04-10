"""Prompt builders for multimodal page understanding."""

from __future__ import annotations

import json
from typing import Any

from src.vision.types import DOMSummary


def build_vision_system_prompt() -> str:
    """Return the system prompt for page understanding."""
    return (
        "You analyze general websites, product sites, docs portals, onboarding flows, and web applications. "
        "Return structured JSON only. "
        "Classify the page type, detect major interface regions, "
        "suggest interaction hints, and provide short extraction hints. "
        "Use page types such as landing, content, docs, list, detail, form, dashboard, auth, modal, or unknown. "
        "Do not assume the site is an admin dashboard unless the screenshot strongly supports that. "
        "Do not suggest actions outside what is visible on screen."
    )


def build_vision_user_prompt(url: str, summary: DOMSummary) -> str:
    """Return the user prompt for a single page."""
    return (
        f"URL: {url}\n"
        f"Title: {summary.title}\n"
        f"DOM component types: {', '.join(summary.component_types) or 'none'}\n"
        f"Visible nav labels: {', '.join(summary.nav_labels) or 'none'}\n"
        f"Visible button labels: {', '.join(summary.button_labels) or 'none'}\n"
        f"Visible tab labels: {', '.join(summary.tab_labels) or 'none'}\n"
        f"Visible table headers: {', '.join(summary.table_headers) or 'none'}\n"
        f"Has modal: {summary.has_modal}\n"
        f"Has table: {summary.has_table}\n"
        f"Has form: {summary.has_form}\n"
        f"Has pagination: {summary.has_pagination}\n"
        "Return JSON with page_type, confidence, regions, interaction_hints, extraction_hints, notes."
    )


def build_candidate_ranking_system_prompt(kind: str) -> str:
    """Return the system prompt for next-step candidate ranking."""
    return (
        "You are helping a website exploration agent choose the next best visible step. "
        f"Rank visible {kind} candidates from the current page. "
        "Return JSON only with keys `choices` and `notes`. "
        "`choices` must be an ordered list of objects shaped like "
        "{\"index\": <candidate index>, \"score\": <0-100>, \"reason\": <short reason>}. "
        "Choose candidates that best advance the user's goal from the current page. "
        "Prefer nearby in-product workflow steps, meaningful navigation, and actions that are likely to reveal new product states. "
        "Avoid legal/privacy, logout, billing, pricing, account recovery, social/community, and marketing detours unless the goal clearly requires them. "
        "Do not invent hidden actions; rank only the provided visible candidates."
    )


def build_candidate_ranking_user_prompt(
    *,
    kind: str,
    goal: str,
    url: str,
    page_type: str,
    dom_summary: DOMSummary,
    interaction_hints: list[dict] | list | None,
    candidates: list[dict[str, Any]],
) -> str:
    """Return the user prompt for candidate ranking."""
    hint_lines: list[str] = []
    for hint in interaction_hints or []:
        if not isinstance(hint, dict):
            continue
        label = str(hint.get("label", "")).strip()
        hint_type = str(hint.get("hint_type", "")).strip()
        if label or hint_type:
            hint_lines.append(f"{hint_type or 'unknown'}: {label or 'unlabeled'}")

    return (
        f"Goal: {goal}\n"
        f"Current URL: {url}\n"
        f"Current page type: {page_type or 'unknown'}\n"
        f"DOM component types: {', '.join(dom_summary.component_types) or 'none'}\n"
        f"Visible nav labels: {', '.join(dom_summary.nav_labels) or 'none'}\n"
        f"Visible button labels: {', '.join(dom_summary.button_labels) or 'none'}\n"
        f"Visible tab labels: {', '.join(dom_summary.tab_labels) or 'none'}\n"
        f"Model interaction hints: {' | '.join(hint_lines) or 'none'}\n"
        f"Candidates ({kind}):\n"
        f"{json.dumps(candidates, ensure_ascii=False, indent=2)}\n"
        "Rank the candidates for what the agent should try next from this page."
    )
