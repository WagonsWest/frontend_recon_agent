"""Artifact manager — handles saving and organizing output artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import AppConfig


class ArtifactManager:
    """Manages output artifact paths and file operations."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._project_root = Path(__file__).parent.parent.parent
        self._analysis_dir = self._project_root / config.output.artifacts_dir / "analysis"
        self._vision_dir = self._project_root / config.output.artifacts_dir / config.vision.artifact_dir
        self._page_insights_dir = self._project_root / config.output.artifacts_dir / config.vision.page_insights_dir
        self._analysis_dir.mkdir(parents=True, exist_ok=True)
        self._vision_dir.mkdir(parents=True, exist_ok=True)
        self._page_insights_dir.mkdir(parents=True, exist_ok=True)

    @property
    def project_root(self) -> Path:
        return self._project_root

    def artifacts_dir(self) -> Path:
        return self._project_root / self.config.output.artifacts_dir

    def reports_dir(self) -> Path:
        return self._project_root / self.config.output.reports_dir

    def analysis_dir(self) -> Path:
        return self._analysis_dir

    def vision_dir(self) -> Path:
        return self._vision_dir

    def page_insights_dir(self) -> Path:
        return self._page_insights_dir

    def save_json(self, filename: str, data: Any, directory: str = "artifacts") -> Path:
        """Save data as JSON. directory can be 'artifacts' or 'reports'."""
        if directory == "reports":
            dir_path = self.reports_dir()
        else:
            dir_path = self.artifacts_dir()
        dir_path.mkdir(parents=True, exist_ok=True)
        path = dir_path / filename
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return path

    def save_analysis(self, state_id: str, data: dict) -> Path:
        """Save per-state analysis result."""
        path = self._analysis_dir / f"{state_id}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return path

    def save_vision(self, state_id: str, data: dict) -> Path:
        """Save per-state vision understanding result."""
        path = self._vision_dir / f"{state_id}_vision.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return path

    def save_page_insight(self, state_id: str, data: dict) -> Path:
        """Save merged per-state page insight result."""
        path = self._page_insights_dir / f"{state_id}_insight.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return path

    def save_jsonl(self, filename: str, rows: list[dict], directory: str = "artifacts") -> Path:
        """Save rows as JSONL."""
        if directory == "reports":
            dir_path = self.reports_dir()
        else:
            dir_path = self.artifacts_dir()
        dir_path.mkdir(parents=True, exist_ok=True)
        path = dir_path / filename
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return path

    def save_text(self, filename: str, content: str, directory: str = "reports") -> Path:
        """Save text/markdown content."""
        if directory == "reports":
            dir_path = self.reports_dir()
        else:
            dir_path = self.artifacts_dir()
        dir_path.mkdir(parents=True, exist_ok=True)
        path = dir_path / filename
        path.write_text(content, encoding="utf-8")
        return path

    def clear_output(self) -> None:
        """Clear all output directories."""
        import shutil
        for dir_name in [
            self.config.output.screenshots_dir,
            self.config.output.dom_snapshots_dir,
            self.config.output.reports_dir,
            self.config.output.artifacts_dir,
        ]:
            dir_path = self._project_root / dir_name
            if dir_path.exists():
                shutil.rmtree(dir_path)
            dir_path.mkdir(parents=True, exist_ok=True)
        self._analysis_dir.mkdir(parents=True, exist_ok=True)
        self._vision_dir.mkdir(parents=True, exist_ok=True)
        self._page_insights_dir.mkdir(parents=True, exist_ok=True)
