"""Configuration loader for Frontend Mimic Agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class TargetConfig(BaseModel):
    url: str
    dashboard_url: str = ""

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"URL must start with http:// or https://, got: {v}")
        return v


class LoginConfig(BaseModel):
    username: str = ""
    password: str = ""
    username_selector: str = "input[type='text'], input[name='username'], input[name='email']"
    password_selector: str = "input[type='password']"
    submit_selector: str = (
        "button[type='submit'], button:has-text('Login'), button:has-text('Sign in'), "
        "button:has-text('登录'), button:has-text('Log in')"
    )
    success_indicator: str = ""


class CrawlConfig(BaseModel):
    wait_after_navigation: int = 3000
    wait_for_spa: int = 2000
    interaction_timeout: int = 10000
    max_interaction_items: int = 5
    exclude_patterns: list[str] = Field(default_factory=lambda: ["/logout", "/api/", ".pdf", ".zip"])


class BudgetConfig(BaseModel):
    max_states: int = 100
    max_depth: int = 5
    retry_limit: int = 2
    novelty_threshold: float = 0.3  # below this, skip deep analysis


class ExplorationConfig(BaseModel):
    """Controls what the agent explores and what it avoids."""
    skip_patterns: list[str] = Field(default_factory=lambda: [
        "/logout", "/api/", ".pdf", ".zip", "javascript:", "mailto:",
    ])
    destructive_keywords: list[str] = Field(default_factory=lambda: [
        "删除", "delete", "remove", "drop", "destroy", "清空", "reset",
    ])
    # Candidate detection: which elements to consider as navigation targets
    nav_selectors: list[str] = Field(default_factory=lambda: [
        "a:has(> .el-menu-item)",           # Element Plus: <a href><li class="el-menu-item">
        ".el-menu-item a[href]",            # Element Plus: <li><a href>
        ".ant-menu-item > a[href]",         # Ant Design
        ".ant-menu-item",                   # Ant Design (no child a)
        "nav a[href]", ".sidebar a[href]", ".side-nav a[href]",
    ])
    # Selectors for collapsed sub-menus that need expanding before nav items are visible
    submenu_expand_selectors: list[str] = Field(default_factory=lambda: [
        ".el-sub-menu:not(.is-opened) > .el-sub-menu__title",
        ".ant-menu-submenu:not(.ant-menu-submenu-open) > .ant-menu-submenu-title",
    ])


class InteractionConfig(BaseModel):
    """Configurable selectors for deep interaction."""
    action_button_selectors: list[str] = Field(default_factory=lambda: [
        "button:has-text('操作')", "button:has-text('Actions')",
        "button:has-text('Action')", ".el-dropdown:has-text('操作') button",
        ".ant-dropdown-trigger", ".dropdown-toggle",
    ])
    add_button_selectors: list[str] = Field(default_factory=lambda: [
        "button:has-text('添加')", "button:has-text('新增')",
        "button:has-text('Add')", "button:has-text('Create')", "button:has-text('New')",
    ])
    dropdown_item_selector: str = (
        ".el-dropdown-menu__item:visible, .ant-dropdown-menu-item:visible, "
        ".dropdown-item:visible, [role='menuitem']:visible"
    )
    # Strict dropdown item selector — excludes [role=menuitem] which may match sidebar nav
    dropdown_item_strict_selector: str = (
        ".el-dropdown-menu__item:visible, .ant-dropdown-menu-item:visible, "
        ".dropdown-item:visible"
    )
    modal_selectors: list[str] = Field(default_factory=lambda: [
        ".el-dialog:visible", ".el-drawer:visible",
        ".ant-modal-wrap:visible", ".modal.show", "[role='dialog']:visible",
    ])
    modal_close_selectors: list[str] = Field(default_factory=lambda: [
        ".el-dialog__headerbtn", ".el-drawer__close-btn",
        ".ant-modal-close", ".modal .btn-close",
        "[aria-label='Close']", ".el-icon--close",
    ])
    overlay_selector: str = ".el-overlay, .ant-modal-mask, .modal-backdrop"
    expand_selectors: list[str] = Field(default_factory=lambda: [
        ".el-table__expand-icon", ".ant-table-row-expand-icon", "td.expand-icon",
    ])
    tab_selector: str = (
        ".el-tabs__item:not(.is-active), .ant-tabs-tab:not(.ant-tabs-tab-active), "
        ".nav-link:not(.active)"
    )


class BrowserConfig(BaseModel):
    headless: bool = False
    viewport_width: int = 1920
    viewport_height: int = 1080
    slow_mo: int = 500
    # CSS selectors for computed style extraction (used in analysis)
    style_selectors: list[str] = Field(default_factory=lambda: [
        "body", "header", "nav", "main", "footer",
        "h1", "h2", "h3", "p", "a", "button",
        ".sidebar", ".navbar", ".container", ".card",
        ".el-dialog", ".el-drawer", ".el-form", ".el-table",
        ".el-aside", ".el-header", ".el-main",
        ".ant-layout-sider", ".ant-layout-header",
        '[class*="sidebar"]', '[class*="navbar"]', '[class*="header"]',
    ])


class OutputConfig(BaseModel):
    screenshots_dir: str = "output/screenshots"
    dom_snapshots_dir: str = "output/dom_snapshots"
    reports_dir: str = "output/reports"
    artifacts_dir: str = "output/artifacts"


class AppConfig(BaseModel):
    target: TargetConfig
    login: LoginConfig = Field(default_factory=LoginConfig)
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    exploration: ExplorationConfig = Field(default_factory=ExplorationConfig)
    interaction: InteractionConfig = Field(default_factory=InteractionConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load configuration from YAML file.

    Priority: settings.local.yaml > settings.yaml > defaults
    Environment variables override: MIMIC_USERNAME, MIMIC_PASSWORD
    """
    project_root = Path(__file__).parent.parent
    config_dir = project_root / "config"

    if config_path:
        path = Path(config_path)
    elif (config_dir / "settings.local.yaml").exists():
        path = config_dir / "settings.local.yaml"
    else:
        path = config_dir / "settings.yaml"

    try:
        with open(path, encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise SystemExit(f"Invalid YAML in {path}: {e}") from e
    except FileNotFoundError:
        raise SystemExit(f"Config file not found: {path}") from None

    config = AppConfig(**data)

    if env_user := os.environ.get("MIMIC_USERNAME"):
        config.login.username = env_user
    if env_pass := os.environ.get("MIMIC_PASSWORD"):
        config.login.password = env_pass

    # Create output directories
    for dir_path in [
        config.output.screenshots_dir,
        config.output.dom_snapshots_dir,
        config.output.reports_dir,
        config.output.artifacts_dir,
    ]:
        try:
            (project_root / dir_path).mkdir(parents=True, exist_ok=True)
        except PermissionError:
            raise SystemExit(f"Permission denied creating directory: {project_root / dir_path}") from None

    return config
