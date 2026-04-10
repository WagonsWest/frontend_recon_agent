"""CLI entry point for Frontend Mimic Agent."""

from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console

from src.agent.batch_runner import BatchRunner
from src.agent.engine import ExplorationEngine
from src.config import apply_run_profile, load_config

console = Console()


async def run_agent(
    config_path: str | None,
    profile: str | None,
    max_states: int | None,
    max_depth: int | None,
    headless: bool,
    clear: bool,
) -> None:
    """Run a single exploration agent."""
    config = load_config(config_path)
    apply_run_profile(config, profile)

    if max_states is not None:
        config.budget.max_states = max_states
    if max_depth is not None:
        config.budget.max_depth = max_depth
    if headless:
        config.browser.headless = True

    engine = ExplorationEngine(config)

    if clear:
        engine.artifacts.clear_output()
        console.print("[green]Output cleared[/green]")

    await engine.run()


async def run_batch(
    batch_config_path: str,
    profile: str | None,
    max_states: int | None,
    max_depth: int | None,
    headless: bool,
    clear: bool,
) -> None:
    """Run a concurrent multi-site batch."""
    runner = BatchRunner()
    summary = await runner.run(
        batch_config_path=batch_config_path,
        profile=profile,
        max_states=max_states,
        max_depth=max_depth,
        headless=headless,
        clear=clear,
    )
    console.print(
        "[green]Batch complete[/green] "
        f"({summary['successful_sites']}/{summary['site_count']} successful). "
        "See batch_summary.json for per-site UX report paths."
    )


async def run_target_urls(
    urls: tuple[str, ...],
    config_path: str | None,
    profile: str | None,
    max_states: int | None,
    max_depth: int | None,
    headless: bool,
    clear: bool,
) -> None:
    """Run one to three ad-hoc URLs using the base config as a template."""
    runner = BatchRunner()
    summary = await runner.run_urls(
        urls=list(urls),
        base_config_path=config_path,
        profile=profile,
        max_states=max_states,
        max_depth=max_depth,
        headless=headless,
        clear=clear,
        max_concurrent_sites=min(3, len(urls)),
    )
    console.print(
        "[green]Ad-hoc batch complete[/green] "
        f"({summary['successful_sites']}/{summary['site_count']} successful). "
        "See batch_summary.json for per-site UX report paths."
    )


def _validate_target_urls(urls: tuple[str, ...]) -> None:
    if not urls:
        return
    if len(urls) > 3:
        raise click.UsageError("Pass at most 3 target URLs at a time.")
    invalid = [url for url in urls if not url.startswith(("http://", "https://"))]
    if invalid:
        joined = ", ".join(invalid)
        raise click.UsageError(f"Target URLs must start with http:// or https://: {joined}")


@click.command()
@click.option("--config", "-c", default=None, help="Path to config YAML file")
@click.option("--batch-config", default=None, help="Path to batch YAML file")
@click.option("--profile", default=None, help="Run profile: default | smoke_fast | demo | full")
@click.option("--max-states", "-s", type=int, default=None, help="Override max states budget")
@click.option("--max-depth", "-d", type=int, default=None, help="Override max exploration depth")
@click.option("--headless", is_flag=True, help="Run browser in headless mode")
@click.option("--clear", is_flag=True, help="Clear output before running")
@click.argument("targets", nargs=-1)
def main(
    config: str | None,
    batch_config: str | None,
    profile: str | None,
    max_states: int | None,
    max_depth: int | None,
    headless: bool,
    clear: bool,
    targets: tuple[str, ...],
) -> None:
    """Frontend Mimic Agent - autonomous website exploration and UI analysis."""
    try:
        _validate_target_urls(targets)
        if config and batch_config:
            raise click.UsageError("Use either --config or --batch-config, not both.")
        if batch_config and targets:
            raise click.UsageError("Use target URLs or --batch-config, not both.")
        if batch_config:
            asyncio.run(run_batch(batch_config, profile, max_states, max_depth, headless, clear))
        elif targets:
            asyncio.run(run_target_urls(targets, config, profile, max_states, max_depth, headless, clear))
        else:
            asyncio.run(run_agent(config, profile, max_states, max_depth, headless, clear))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
