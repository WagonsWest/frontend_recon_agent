"""Extraction strategy dispatcher."""

from __future__ import annotations

from src.extraction.detail_extractor import DetailExtractor
from src.extraction.form_extractor import FormExtractor
from src.extraction.list_extractor import ListExtractor
from src.extraction.types import EvidencePaths, ExtractionResult


class ExtractionEngine:
    """Dispatches extraction based on the chosen strategy."""

    def __init__(self) -> None:
        self._list = ListExtractor()
        self._detail = DetailExtractor()
        self._form = FormExtractor()

    def extract(self, html: str, state_id: str, target_id: str, url: str,
                page_type: str, strategy: str, evidence_paths: EvidencePaths) -> ExtractionResult:
        """Run the selected extraction strategy."""
        try:
            if strategy == "list_table":
                return self._list.extract(html, state_id, target_id, url, page_type, evidence_paths)
            if strategy == "detail_fields":
                return self._detail.extract(html, state_id, target_id, url, page_type, evidence_paths)
            if strategy == "form_schema":
                return self._form.extract(html, state_id, target_id, url, page_type, evidence_paths)
            return ExtractionResult(
                state_id=state_id,
                target_id=target_id,
                url=url,
                page_type=page_type,
                strategy="unknown",
                status="skipped",
                evidence_paths=evidence_paths,
                summary={"reason": "unknown extraction strategy"},
            )
        except Exception as e:
            return ExtractionResult(
                state_id=state_id,
                target_id=target_id,
                url=url,
                page_type=page_type,
                strategy=strategy if strategy in {"list_table", "detail_fields", "form_schema"} else "unknown",
                status="failed",
                evidence_paths=evidence_paths,
                error=str(e),
            )
