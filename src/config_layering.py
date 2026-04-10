"""Config layering helpers: presets plus optional site-pattern overrides."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel

if TYPE_CHECKING:
    from src.config import AppConfig


GENERIC_NAV_SELECTORS = [
    "nav a[href]",
    "header nav a[href]",
    "[role='navigation'] a[href]",
    ".sidebar a[href]",
    ".side-nav a[href]",
]

ADMIN_NAV_SELECTORS = [
    "a:has(> .el-menu-item)",
    ".el-menu-item a[href]",
    ".ant-menu-item > a[href]",
    ".ant-menu-item",
]

GENERIC_SUBMENU_EXPAND_SELECTORS = [
    "[aria-haspopup='menu'][aria-expanded='false']",
]

ADMIN_SUBMENU_EXPAND_SELECTORS = [
    ".el-sub-menu:not(.is-opened) > .el-sub-menu__title",
    ".ant-menu-submenu:not(.ant-menu-submenu-open) > .ant-menu-submenu-title",
]

GENERIC_ACTION_BUTTON_SELECTORS = [
    "button:has-text('Actions')",
    "button:has-text('Action')",
    ".dropdown-toggle",
]

ADMIN_ACTION_BUTTON_SELECTORS = [
    ".el-dropdown button",
    ".ant-dropdown-trigger",
]

GENERIC_ADD_BUTTON_SELECTORS = [
    "button:has-text('Add')",
    "button:has-text('Create')",
    "button:has-text('New')",
]

ADMIN_ADD_BUTTON_SELECTORS = [
    ".el-button",
]

GENERIC_MODAL_SELECTORS = [
    ".modal.show",
    "[role='dialog']:visible",
]

ADMIN_MODAL_SELECTORS = [
    ".el-dialog:visible",
    ".el-drawer:visible",
    ".ant-modal-wrap:visible",
]

GENERIC_MODAL_CLOSE_SELECTORS = [
    "[aria-label='Close']",
    ".modal .btn-close",
]

ADMIN_MODAL_CLOSE_SELECTORS = [
    ".el-dialog__headerbtn",
    ".el-drawer__close-btn",
    ".ant-modal-close",
    ".el-icon--close",
]

GENERIC_EXPAND_SELECTORS = [
    "td.expand-icon",
]

ADMIN_EXPAND_SELECTORS = [
    ".el-table__expand-icon",
    ".ant-table-row-expand-icon",
]

GENERIC_TAB_SELECTOR = ".nav-link:not(.active), [role='tab'][aria-selected='false']"
ADMIN_TAB_SELECTOR = (
    ".el-tabs__item:not(.is-active), .ant-tabs-tab:not(.ant-tabs-tab-active), "
    ".nav-link:not(.active), [role='tab'][aria-selected='false']"
)

GENERIC_STYLE_SELECTORS = [
    "body", "header", "nav", "main", "footer",
    "h1", "h2", "h3", "p", "a", "button",
    ".sidebar", ".navbar", ".container", ".card",
    '[class*="sidebar"]', '[class*="navbar"]', '[class*="header"]',
]

ADMIN_STYLE_SELECTORS = [
    ".el-dialog", ".el-drawer", ".el-form", ".el-table",
    ".el-aside", ".el-header", ".el-main",
    ".ant-layout-sider", ".ant-layout-header",
]

GENERAL_HIGH_VALUE_PATH_HINTS = [
    "docs", "documentation", "guide", "pricing", "about",
    "product", "products", "platform", "features", "solutions",
    "compare", "comparison", "faq", "contact", "article", "articles",
    "report", "reports",
]

COMPETITIVE_HIGH_VALUE_PATH_HINTS = [
    "benchmark", "benchmarks", "model", "models", "evaluation", "evaluations",
    "leaderboard", "trend", "trends", "provider", "providers",
    "methodology", "research", "image", "video", "speech", "audio",
]


def _extend_unique(items: list[str], additions: list[str]) -> list[str]:
    seen = {item for item in items}
    merged = list(items)
    for item in additions:
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return merged


def _apply_selector_preset(config: "AppConfig") -> None:
    preset = (config.layering.selector_preset or "general_web").strip().lower()
    if preset in {"", "none", "general_web"}:
        return
    if preset in {"admin_ui", "hybrid_admin"}:
        config.exploration.nav_selectors = _extend_unique(config.exploration.nav_selectors, ADMIN_NAV_SELECTORS)
        config.exploration.submenu_expand_selectors = _extend_unique(
            config.exploration.submenu_expand_selectors,
            ADMIN_SUBMENU_EXPAND_SELECTORS,
        )
        config.interaction.action_button_selectors = _extend_unique(
            config.interaction.action_button_selectors,
            ADMIN_ACTION_BUTTON_SELECTORS,
        )
        config.interaction.add_button_selectors = _extend_unique(
            config.interaction.add_button_selectors,
            ADMIN_ADD_BUTTON_SELECTORS,
        )
        config.interaction.modal_selectors = _extend_unique(
            config.interaction.modal_selectors,
            ADMIN_MODAL_SELECTORS,
        )
        config.interaction.modal_close_selectors = _extend_unique(
            config.interaction.modal_close_selectors,
            ADMIN_MODAL_CLOSE_SELECTORS,
        )
        config.interaction.expand_selectors = _extend_unique(
            config.interaction.expand_selectors,
            ADMIN_EXPAND_SELECTORS,
        )
        config.browser.style_selectors = _extend_unique(
            config.browser.style_selectors,
            ADMIN_STYLE_SELECTORS,
        )
        config.interaction.tab_selector = ADMIN_TAB_SELECTOR
        return
    raise SystemExit(f"Unsupported selector preset: {config.layering.selector_preset}")


def _apply_heuristic_preset(config: "AppConfig") -> None:
    """Heuristic presets are disabled; runtime prioritization is model-led."""
    return


def _resolve_site_pattern_path(config: "AppConfig", project_root: Path) -> Path | None:
    site_pattern = (config.target.site_pattern or "auto").strip()
    if not config.layering.site_patterns_enabled:
        return None
    if site_pattern.lower() in {"off", "none", "disabled"}:
        return None
    if site_pattern.lower() == "auto":
        domain = urlparse(config.target.url).netloc.lower()
        if not domain:
            return None
        candidate = project_root / config.layering.site_patterns_dir / f"{domain}.yaml"
        return candidate if candidate.exists() else None

    candidate = Path(site_pattern)
    if not candidate.is_absolute():
        candidate = project_root / site_pattern
    return candidate if candidate.exists() else None


def _merge_model(model: BaseModel, overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        if not hasattr(model, key):
            continue
        current = getattr(model, key)
        if isinstance(current, BaseModel) and isinstance(value, dict):
            _merge_model(current, value)
            continue
        if isinstance(current, list) and isinstance(value, list):
            setattr(model, key, _extend_unique(current, [str(item) for item in value]))
            continue
        setattr(model, key, value)


def _apply_site_pattern(config: "AppConfig", project_root: Path) -> None:
    pattern_path = _resolve_site_pattern_path(config, project_root)
    if pattern_path is None:
        return

    try:
        with open(pattern_path, encoding="utf-8") as f:
            overrides = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise SystemExit(f"Invalid YAML in site pattern {pattern_path}: {e}") from e
    except FileNotFoundError:
        return

    if not isinstance(overrides, dict):
        raise SystemExit(f"Site pattern {pattern_path} must be a mapping")
    _merge_model(config, overrides)


def apply_config_layering(config: "AppConfig", project_root: Path) -> None:
    """Apply explicit config layers so defaults can stay more generic."""
    _apply_selector_preset(config)
    _apply_heuristic_preset(config)
    _apply_site_pattern(config, project_root)
