"""Typed models for vision-assisted page understanding."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PageType = Literal["list", "detail", "form", "dashboard", "modal", "unknown"]
RegionType = Literal[
    "sidebar", "topnav", "filter_bar", "table", "detail_panel", "form",
    "modal", "drawer", "tabs", "pagination", "toolbar", "unknown",
]
HintType = Literal[
    "primary_action", "row_actions", "tab_switch", "open_modal",
    "open_detail", "paginate", "filter", "unknown",
]


class DOMSummary(BaseModel):
    title: str = ""
    component_types: list[str] = Field(default_factory=list)
    nav_labels: list[str] = Field(default_factory=list)
    button_labels: list[str] = Field(default_factory=list)
    tab_labels: list[str] = Field(default_factory=list)
    table_headers: list[str] = Field(default_factory=list)
    has_modal: bool = False
    has_table: bool = False
    has_form: bool = False
    has_pagination: bool = False


class VisionRegion(BaseModel):
    region_type: RegionType = "unknown"
    label: str = ""
    bbox_norm: list[float] = Field(default_factory=list)
    confidence: float = 0.0


class InteractionHint(BaseModel):
    hint_type: HintType = "unknown"
    target_region: str = ""
    label: str = ""
    confidence: float = 0.0


class VisionResult(BaseModel):
    page_type: PageType = "unknown"
    confidence: float = 0.0
    regions: list[VisionRegion] = Field(default_factory=list)
    interaction_hints: list[InteractionHint] = Field(default_factory=list)
    extraction_hints: list[str] = Field(default_factory=list)
    notes: str = ""


class PageInsight(BaseModel):
    state_id: str
    url: str = ""
    page_type_dom: str = "unknown"
    page_type_vision: PageType = "unknown"
    dom_component_types: list[str] = Field(default_factory=list)
    vision_regions: list[VisionRegion] = Field(default_factory=list)
    interaction_hints: list[InteractionHint] = Field(default_factory=list)
    extraction_strategy: str = "unknown"
    high_value_page: bool = False
    analysis_tags: list[str] = Field(default_factory=list)

