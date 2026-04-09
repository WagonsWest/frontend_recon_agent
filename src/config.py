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
    mode: str = "auto"
    username: str = ""
    password: str = ""
    register_url: str = ""
    register_link_selector: str = ""
    username_selector: str = "input[type='text'], input[name='username'], input[name='email']"
    password_selector: str = "input[type='password']"
    submit_selector: str = (
        "form button[type='submit'], form input[type='submit'], button[type='submit'], button:has-text('Login'), button:has-text('Sign in'), "
        "button:has-text('登录'), button:has-text('Log in')"
    )
    success_indicator: str = ""
    registration_name_selector: str = (
        "input[name='name'], input[name='full_name'], input[name='fullname'], "
        "input[autocomplete='name']"
    )
    registration_email_selector: str = "input[type='email'], input[name='email']"
    registration_password_selector: str = (
        "input[type='password'], input[name='password'], input[autocomplete='new-password']"
    )
    registration_confirm_password_selector: str = (
        "input[name='confirm_password'], input[name='password_confirmation'], "
        "input[name='confirmPassword']"
    )
    registration_company_selector: str = (
        "input[name='company'], input[name='organization'], input[name='org'], input[name='workspace']"
    )
    registration_submit_selector: str = (
        "form button[type='submit'], form input[type='submit'], button[type='submit'], button:has-text('Sign up'), button:has-text('Get started'), "
        "button:has-text('Create account'), button:has-text('Register')"
    )
    registration_success_indicator: str = ""
    verification_code_selector: str = (
        "input[autocomplete='one-time-code'], input[name*='code'], input[id*='code'], "
        "input[name*='otp'], input[id*='otp'], input[inputmode='numeric']"
    )
    verification_submit_selector: str = (
        "form button[type='submit'], form input[type='submit'], button[type='submit'], button:has-text('Verify'), button:has-text('Continue'), "
        "button:has-text('Confirm'), button:has-text('Activate')"
    )


class TaskConfig(BaseModel):
    goal: str = "Explore the target website and understand its product surfaces."
    goal_keywords: list[str] = Field(default_factory=list)
    allow_registration_flows: bool = True
    allow_login_flows: bool = True
    captcha_policy: str = "pause_and_report"
    human_assistance_allowed: bool = True
    use_site_memory: bool = True
    validate_action_outcomes: bool = True
    reobserve_on_state_change: bool = True
    use_vision_on_state_change: bool = True
    max_reobservations_per_run: int = 30
    profile_name: str = "Test User"
    profile_email: str = "test@example.com"
    profile_password: str = "TestPassword123!"
    profile_company: str = "Example Inc"


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
    novelty_threshold: float = 0.12  # below this, skip capture entirely


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
    max_route_candidates_per_page: int = 40
    high_value_path_hints: list[str] = Field(default_factory=lambda: [
        "benchmark", "benchmarks", "model", "models", "evaluation", "evaluations",
        "leaderboard", "arena", "trend", "trends", "pricing", "provider", "providers",
        "article", "articles", "methodology", "guide", "docs", "documentation",
        "research", "report", "reports", "image", "video", "speech", "audio",
        "compare", "comparison", "faq",
    ])
    low_value_path_hints: list[str] = Field(default_factory=lambda: [
        "privacy", "terms", "legal", "cookie", "cookies", "mailto:",
        "x.com", "twitter.com", "linkedin.com", "discord.gg", "youtube.com",
    ])
    # Selectors for collapsed sub-menus that need expanding before nav items are visible
    submenu_expand_selectors: list[str] = Field(default_factory=lambda: [
        ".el-sub-menu:not(.is-opened) > .el-sub-menu__title",
        ".ant-menu-submenu:not(.ant-menu-submenu-open) > .ant-menu-submenu-title",
        "nav button[aria-expanded='false']",
        "nav [role='button'][aria-expanded='false']",
        "header button[aria-expanded='false']",
        "header [role='button'][aria-expanded='false']",
        "[role='navigation'] button[aria-expanded='false']",
        "[role='navigation'] [role='button'][aria-expanded='false']",
        "[aria-haspopup='menu'][aria-expanded='false']",
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


class VisionConfig(BaseModel):
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-5.4"
    api_base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    timeout_ms: int = 15000
    max_image_side: int = 1440
    artifact_dir: str = "vision"
    page_insights_dir: str = "page_insights"


class SynthesisConfig(BaseModel):
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4.1-mini"
    api_base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    timeout_ms: int = 20000
    artifact_filename_json: str = "competitive_analysis_llm.json"
    artifact_filename_md: str = "competitive_analysis.md"
    structured_report_filename_md: str = "competitive_analysis_structured.md"
    readable_report_filename_md: str = "competitive_analysis_readable.md"


class OutputConfig(BaseModel):
    screenshots_dir: str = "output/screenshots"
    dom_snapshots_dir: str = "output/dom_snapshots"
    reports_dir: str = "output/reports"
    artifacts_dir: str = "output/artifacts"


class RunConfig(BaseModel):
    profile: str = "default"
    navigation_wait_until: str = "networkidle"
    enable_page_action_planning: bool = True
    enable_interaction_exploration: bool = True
    enable_extraction: bool = True
    capture_report_screenshots: bool = True
    enable_timing_summary: bool = True


class BatchSiteConfig(BaseModel):
    name: str
    config: str
    max_states: int | None = None
    max_depth: int | None = None


class BatchRunConfig(BaseModel):
    name: str = ""
    output_root: str = "output/batch"
    sites: list[BatchSiteConfig] = Field(default_factory=list)


class AppConfig(BaseModel):
    target: TargetConfig
    task: TaskConfig = Field(default_factory=TaskConfig)
    login: LoginConfig = Field(default_factory=LoginConfig)
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    exploration: ExplorationConfig = Field(default_factory=ExplorationConfig)
    interaction: InteractionConfig = Field(default_factory=InteractionConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    synthesis: SynthesisConfig = Field(default_factory=SynthesisConfig)
    run: RunConfig = Field(default_factory=RunConfig)
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


def load_batch_config(config_path: str | Path) -> tuple[BatchRunConfig, Path]:
    """Load a batch-run config and return it with its base directory."""
    path = Path(config_path)

    try:
        with open(path, encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise SystemExit(f"Invalid YAML in {path}: {e}") from e
    except FileNotFoundError:
        raise SystemExit(f"Batch config file not found: {path}") from None

    config = BatchRunConfig(**data)
    if not config.sites:
        raise SystemExit(f"Batch config {path} must include at least one site entry")
    return config, path.parent.resolve()


def apply_run_profile(config: AppConfig, profile_name: str | None) -> str:
    """Apply a named run profile to the in-memory config."""
    selected = (profile_name or config.run.profile or "default").strip().lower()
    config.run.profile = selected

    if selected == "default":
        return selected

    if selected == "smoke_fast":
        config.run.navigation_wait_until = "domcontentloaded"
        config.run.enable_page_action_planning = False
        config.run.enable_interaction_exploration = False
        config.run.enable_extraction = False
        config.run.capture_report_screenshots = False
        config.browser.slow_mo = 0
        config.crawl.wait_after_navigation = min(config.crawl.wait_after_navigation, 500)
        config.crawl.wait_for_spa = min(config.crawl.wait_for_spa, 700)
        config.crawl.interaction_timeout = min(config.crawl.interaction_timeout, 2500)
        config.budget.max_states = min(config.budget.max_states, 4)
        config.budget.max_depth = min(config.budget.max_depth, 1)
        config.task.reobserve_on_state_change = False
        config.task.use_vision_on_state_change = False
        config.vision.enabled = False
        config.synthesis.enabled = False
        return selected

    if selected == "demo":
        config.run.navigation_wait_until = "domcontentloaded"
        config.run.enable_page_action_planning = True
        config.run.enable_interaction_exploration = True
        config.run.enable_extraction = True
        config.run.capture_report_screenshots = True
        config.browser.slow_mo = min(config.browser.slow_mo, 100)
        config.crawl.wait_after_navigation = min(config.crawl.wait_after_navigation, 1200)
        config.crawl.wait_for_spa = min(config.crawl.wait_for_spa, 1200)
        config.synthesis.enabled = False
        return selected

    if selected == "full":
        config.run.navigation_wait_until = "networkidle"
        config.run.enable_page_action_planning = True
        config.run.enable_interaction_exploration = True
        config.run.enable_extraction = True
        config.run.capture_report_screenshots = True
        return selected

    raise SystemExit(f"Unsupported run profile: {selected}")
