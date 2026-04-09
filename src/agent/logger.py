"""Structured run logger — writes JSONL execution log."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Generator

from src.agent.state import AgentPhase


@dataclass
class RunLogEntry:
    step: int
    timestamp: str
    phase: str
    action: str
    target: str
    result: str  # "success", "failed", "skipped", "retry"
    reason: str
    duration_ms: int


class RunLogger:
    """Appends structured log entries to a JSONL file."""

    def __init__(self, log_path: Path):
        self._path = log_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "w", encoding="utf-8")
        self._step = 0
        self._entries: list[RunLogEntry] = []

    def log(self, phase: AgentPhase, action: str, target: str,
            result: str, reason: str, duration_ms: int = 0) -> RunLogEntry:
        self._step += 1
        entry = RunLogEntry(
            step=self._step,
            timestamp=datetime.now().isoformat(),
            phase=phase.value,
            action=action,
            target=target,
            result=result,
            reason=reason,
            duration_ms=duration_ms,
        )
        self._file.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        self._file.flush()
        self._entries.append(entry)
        return entry

    @contextmanager
    def timed(self, phase: AgentPhase, action: str, target: str = "") -> Generator[dict, None, None]:
        """Context manager that auto-logs with timing. Caller sets result/reason on the dict."""
        ctx = {"result": "success", "reason": ""}
        start = time.monotonic()
        try:
            yield ctx
        except Exception as e:
            ctx["result"] = "failed"
            ctx["reason"] = str(e)
            raise
        finally:
            elapsed = int((time.monotonic() - start) * 1000)
            self.log(phase, action, target, ctx["result"], ctx["reason"], elapsed)

    def close(self) -> None:
        if self._file and not self._file.closed:
            self._file.close()

    @property
    def step_count(self) -> int:
        return self._step

    def summary(self) -> dict:
        """Return aggregate timing stats by phase and action."""
        phase_stats: dict[str, dict[str, int]] = {}
        action_stats: dict[str, dict[str, int]] = {}

        for entry in self._entries:
            phase_bucket = phase_stats.setdefault(entry.phase, {"count": 0, "duration_ms": 0})
            phase_bucket["count"] += 1
            phase_bucket["duration_ms"] += entry.duration_ms

            action_key = f"{entry.phase}:{entry.action}"
            action_bucket = action_stats.setdefault(action_key, {"count": 0, "duration_ms": 0})
            action_bucket["count"] += 1
            action_bucket["duration_ms"] += entry.duration_ms

        return {
            "total_steps": self._step,
            "total_duration_ms": sum(entry.duration_ms for entry in self._entries),
            "by_phase": phase_stats,
            "by_action": action_stats,
        }
