"""Prompt builders for multimodal page understanding."""

from __future__ import annotations

from src.vision.types import DOMSummary


def build_vision_system_prompt() -> str:
    """Return the system prompt for page understanding."""
    return (
        "You analyze admin and SaaS web application screenshots. "
        "Return structured JSON only. "
        "Classify the page type, detect major interface regions, "
        "suggest interaction hints, and provide short extraction hints. "
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
