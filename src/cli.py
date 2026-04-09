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
    if headless or config.browser.headless:
        console.print(
            "[yellow]Visible browser mode is enforced for interactive auth and verification; ignoring headless setting.[/yellow]"
        )
    config.browser.headless = False

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
        f"Comparison: {summary['comparison_report']}"
    )


@click.command()
@click.option("--config", "-c", default=None, help="Path to config YAML file")
@click.option("--batch-config", default=None, help="Path to batch YAML file")
@click.option("--profile", default=None, help="Run profile: default | smoke_fast | demo | full")
@click.option("--max-states", "-s", type=int, default=None, help="Override max states budget")
@click.option("--max-depth", "-d", type=int, default=None, help="Override max exploration depth")
@click.option("--headless", is_flag=True, help="Deprecated for interactive auth flows; browser stays visible")
@click.option("--clear", is_flag=True, help="Clear output before running")
def main(
    config: str | None,
    batch_config: str | None,
    profile: str | None,
    max_states: int | None,
    max_depth: int | None,
    headless: bool,
    clear: bool,
) -> None:
    """Frontend Mimic Agent - autonomous website exploration and UI analysis."""
    try:
        if config and batch_config:
            raise click.UsageError("Use either --config or --batch-config, not both.")
        if batch_config:
            asyncio.run(run_batch(batch_config, profile, max_states, max_depth, headless, clear))
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
