"""Rich progress display and user interaction for the pipeline."""

from __future__ import annotations

import asyncio
import logging

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt

console = Console()

# Module-level reference so ask_user can pause/resume the active progress display.
_active_progress: PipelineProgress | None = None


class PipelineProgress:
    """Tracks progress across the multi-agent pipeline using Rich."""

    def __init__(self) -> None:
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        )
        self._task_ids: dict[str, int] = {}

    def __enter__(self) -> "PipelineProgress":
        global _active_progress
        self._progress.__enter__()
        _active_progress = self
        return self

    def __exit__(self, *args: object) -> None:
        global _active_progress
        _active_progress = None
        self._progress.__exit__(*args)

    def pause(self) -> None:
        """Temporarily stop the live display (e.g. before prompting for input)."""
        self._progress.stop()

    def resume(self) -> None:
        """Restart the live display after a pause."""
        self._progress.start()

    def start_agent(self, agent_name: str) -> None:
        """Register and start tracking an agent."""
        tid = self._progress.add_task(f"[cyan]{agent_name}[/]", total=None)
        self._task_ids[agent_name] = tid

    def update_agent(self, agent_name: str, status: str) -> None:
        """Update the status text for an agent."""
        if agent_name in self._task_ids:
            self._progress.update(
                self._task_ids[agent_name],
                description=f"[cyan]{agent_name}[/] — {status}",
            )

    def finish_agent(self, agent_name: str) -> None:
        """Mark an agent as complete."""
        if agent_name in self._task_ids:
            self._progress.update(
                self._task_ids[agent_name],
                description=f"[green]✓ {agent_name}[/]",
                completed=True,
            )

    def fail_agent(self, agent_name: str, error: str) -> None:
        """Mark an agent as failed."""
        if agent_name in self._task_ids:
            self._progress.update(
                self._task_ids[agent_name],
                description=f"[red]✗ {agent_name}: {error}[/]",
                completed=True,
            )

    def log_event(self, agent_name: str, message: str, style: str = "dim") -> None:
        """Print a persistent log line above the spinner (not overwritten)."""
        self._progress.console.print(f"  [{style}]{agent_name}:[/] {message}")

    def print_phase(self, label: str) -> None:
        """Print a phase header outside the progress display."""
        self._progress.console.print(Panel(f"[bold]{label}[/bold]", style="blue"))


async def ask_user(question: str) -> str:
    """Prompt the user for input (runs in executor to avoid blocking the event loop).

    Pauses the Rich progress display while waiting so the prompt is visible
    and stdin is not contended.  Falls back gracefully when stdin is not
    available (e.g. running in a non-interactive context like a subprocess or CI).
    """
    import sys

    if not sys.stdin.isatty():
        console.print(f"[yellow]Agent question (non-interactive, skipped):[/] {question}")
        return "(No user input available — running in non-interactive mode. Please proceed with your best judgment.)"

    # Pause the live spinner and suppress log output so the prompt renders cleanly.
    if _active_progress is not None:
        _active_progress.pause()

    # Temporarily raise the root log level to suppress httpx / agent chatter
    root_logger = logging.getLogger()
    prev_level = root_logger.level
    root_logger.setLevel(logging.CRITICAL)

    loop = asyncio.get_running_loop()
    try:
        answer = await loop.run_in_executor(
            None, lambda: Prompt.ask(f"\n[yellow]Agent question:[/] {question}")
        )
        return answer
    except EOFError:
        return "(No user input available. Please proceed with your best judgment.)"
    finally:
        root_logger.setLevel(prev_level)
        if _active_progress is not None:
            _active_progress.resume()
