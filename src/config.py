"""Configuration loader for Frontend Mimic Agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from src.config_layering import (
    GENERIC_ACTION_BUTTON_SELECTORS,
    GENERIC_ADD_BUTTON_SELECTORS,
    GENERIC_EXPAND_SELECTORS,
    GENERIC_MODAL_CLOSE_SELECTORS,
    GENERIC_MODAL_SELECTORS,
    GENERIC_NAV_SELECTORS,
    GENERIC_STYLE_SELECTORS,
    GENERIC_SUBMENU_EXPAND_SELECTORS,
    GENERIC_TAB_SELECTOR,
    apply_config_layering,
)


class TargetConfig(BaseModel):
    url: str
    dashboard_url: str = ""
    site_pattern: str = "auto"

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
        "form button[type='submit'], form input[type='submit'], button[type='submit'], "
        "button:has-text('Login'), button:has-text('Sign in'), button:has-text('Log in')"
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
        "form button[type='submit'], form input[type='submit'], button[type='submit'], "
        "button:has-text('Sign up'), button:has-text('Get started'), "
        "button:has-text('Create account'), button:has-text('Register')"
    )
    registration_success_indicator: str = ""
    verification_code_selector: str = (
        "input[autocomplete='one-time-code'], input[name*='code'], input[id*='code'], "
        "input[name*='otp'], input[id*='otp'], input[inputmode='numeric']"
    )
    verification_submit_selector: str = (
        "form button[type='submit'], form input[type='submit'], button[type='submit'], "
        "button:has-text('Verify'), button:has-text('Continue'), "
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
    novelty_threshold: float = 0.12


class ExplorationConfig(BaseModel):
    """Controls what the agent explores and what it avoids."""

    skip_patterns: list[str] = Field(default_factory=lambda: [
        "/logout", "/api/", ".pdf", ".zip", "javascript:", "mailto:",
    ])
    destructive_keywords: list[str] = Field(default_factory=lambda: [
        "delete", "remove", "drop", "destroy", "reset",
    ])
    nav_selectors: list[str] = Field(default_factory=lambda: list(GENERIC_NAV_SELECTORS))
    max_route_candidates_per_page: int = 40
    high_value_path_hints: list[str] = Field(default_factory=list)
    auth_risk_path_hints: list[str] = Field(default_factory=list)
    interactive_risk_path_hints: list[str] = Field(default_factory=list)
    low_value_path_hints: list[str] = Field(default_factory=list)
    submenu_expand_selectors: list[str] = Field(default_factory=lambda: list(GENERIC_SUBMENU_EXPAND_SELECTORS))
    hover_menu_trigger_selectors: list[str] = Field(default_factory=lambda: [
        "nav a[href]",
        "nav button",
        "nav [role='button']",
        "nav [role='menuitem']",
        "header nav a[href]",
        "header nav button",
        "header nav [role='button']",
        "header nav [role='menuitem']",
        "[role='navigation'] a[href]",
        "[role='navigation'] button",
        "[role='navigation'] [role='button']",
        "[role='navigation'] [role='menuitem']",
        "[aria-haspopup='menu']",
    ])
    hover_menu_nested_selectors: list[str] = Field(default_factory=lambda: [
        "[role='menu'] a[href]",
        "[role='menu'] button",
        "[role='menu'] [role='menuitem']",
        "[class*='menu'] a[href]",
        "[class*='menu'] button",
        "[class*='dropdown'] a[href]",
        "[class*='dropdown'] button",
        "[class*='popover'] a[href]",
        "[class*='popover'] button",
        "[data-radix-popper-content-wrapper] a[href]",
        "[data-radix-popper-content-wrapper] button",
        "[data-headlessui-state] a[href]",
        "[data-headlessui-state] button",
    ])
    hover_menu_wait_ms: int = 250
    hover_menu_max_triggers: int = 6
    hover_menu_max_depth: int = 2


class InteractionConfig(BaseModel):
    """Configurable selectors for deep interaction."""

    action_button_selectors: list[str] = Field(default_factory=lambda: list(GENERIC_ACTION_BUTTON_SELECTORS))
    add_button_selectors: list[str] = Field(default_factory=lambda: list(GENERIC_ADD_BUTTON_SELECTORS))
    dropdown_item_selector: str = (
        ".el-dropdown-menu__item:visible, .ant-dropdown-menu-item:visible, "
        ".dropdown-item:visible, [role='menuitem']:visible"
    )
    dropdown_item_strict_selector: str = (
        ".el-dropdown-menu__item:visible, .ant-dropdown-menu-item:visible, "
        ".dropdown-item:visible"
    )
    modal_selectors: list[str] = Field(default_factory=lambda: list(GENERIC_MODAL_SELECTORS))
    modal_close_selectors: list[str] = Field(default_factory=lambda: list(GENERIC_MODAL_CLOSE_SELECTORS))
    overlay_selector: str = ".el-overlay, .ant-modal-mask, .modal-backdrop"
    expand_selectors: list[str] = Field(default_factory=lambda: list(GENERIC_EXPAND_SELECTORS))
    tab_selector: str = GENERIC_TAB_SELECTOR


class BrowserConfig(BaseModel):
    headless: bool = False
    viewport_width: int = 1920
    viewport_height: int = 1080
    slow_mo: int = 500
    style_selectors: list[str] = Field(default_factory=lambda: list(GENERIC_STYLE_SELECTORS))


class VisionConfig(BaseModel):
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-5.4"
    api_base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    timeout_ms: int = 15000
    max_image_side: int = 1440
    max_concurrent_requests: int = 2
    artifact_dir: str = "vision"
    page_insights_dir: str = "page_insights"


class SynthesisConfig(BaseModel):
    ux_report_filename_md: str = "ux_report.md"


class OutputConfig(BaseModel):
    screenshots_dir: str = "output/screenshots"
    dom_snapshots_dir: str = "output/dom_snapshots"
    reports_dir: str = "output/reports"
    artifacts_dir: str = "output/artifacts"


class LayeringConfig(BaseModel):
    selector_preset: str = "general_web"
    heuristic_preset: str = "none"
    site_patterns_enabled: bool = True
    site_patterns_dir: str = "config/site_patterns"


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
    max_concurrent_sites: int = 3
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
    layering: LayeringConfig = Field(default_factory=LayeringConfig)


def _resolve_config_path(config_path: str | Path | None = None) -> Path | None:
    project_root = Path(__file__).parent.parent
    config_dir = project_root / "config"

    if config_path:
        path: Path | None = Path(config_path)
    elif (config_dir / "settings.local.yaml").exists():
        path = config_dir / "settings.local.yaml"
    elif (config_dir / "settings.yaml").exists():
        path = config_dir / "settings.yaml"
    else:
        path = None
    return path


def _load_yaml_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise SystemExit(f"Invalid YAML in {path}: {e}") from e
    except FileNotFoundError:
        raise SystemExit(f"Config file not found: {path}") from None


def _finalize_config(config: AppConfig, project_root: Path) -> AppConfig:
    apply_config_layering(config, project_root)

    if env_user := os.environ.get("MIMIC_USERNAME"):
        config.login.username = env_user
    if env_pass := os.environ.get("MIMIC_PASSWORD"):
        config.login.password = env_pass

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


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load configuration from YAML file.

    Priority: explicit config > settings.local.yaml > settings.yaml
    Environment variables override: MIMIC_USERNAME, MIMIC_PASSWORD
    """
    project_root = Path(__file__).parent.parent
    path = _resolve_config_path(config_path)
    if path is None:
        raise SystemExit(
            "No config file found. Pass --config PATH or create a local config/settings.local.yaml."
        )

    data = _load_yaml_config(path)
    config = AppConfig(**data)
    return _finalize_config(config, project_root)


def load_config_for_url(target_url: str, config_path: str | Path | None = None) -> AppConfig:
    """Load configuration while overriding the target URL before layering is applied."""
    project_root = Path(__file__).parent.parent
    path = _resolve_config_path(config_path)
    data = _load_yaml_config(path)
    target_data = data.get("target") or {}
    if not isinstance(target_data, dict):
        raise SystemExit(f"Config file {path} has invalid target section")
    target_data["url"] = target_url
    data["target"] = target_data

    config = AppConfig(**data)
    return _finalize_config(config, project_root)


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
        return selected

    if selected == "demo":
        config.run.navigation_wait_until = "domcontentloaded"
        config.browser.slow_mo = min(config.browser.slow_mo, 100)
        config.crawl.wait_after_navigation = min(config.crawl.wait_after_navigation, 1200)
        config.crawl.wait_for_spa = min(config.crawl.wait_for_spa, 1200)
        return selected

    if selected == "full":
        config.run.navigation_wait_until = "networkidle"
        return selected

    raise SystemExit(f"Unsupported run profile: {selected}")
