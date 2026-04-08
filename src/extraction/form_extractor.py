"""Form/schema extractor."""

from __future__ import annotations

from bs4 import BeautifulSoup

from src.extraction.types import EvidencePaths, ExtractionResult


class FormExtractor:
    """Extracts form field schema from visible inputs and form items."""

    def extract(self, html: str, state_id: str, target_id: str, url: str,
                page_type: str, evidence_paths: EvidencePaths) -> ExtractionResult:
        soup = BeautifulSoup(html, "lxml")
        fields: list[dict[str, str | bool]] = []

        elements = soup.select("input, select, textarea")
        for element in elements[:50]:
            input_type = element.get("type", "text")
            if input_type == "hidden":
                continue

            field_name = (
                element.get("name")
                or element.get("placeholder")
                or element.get("id")
                or element.get("aria-label")
                or ""
            )
            required = element.has_attr("required") or element.get("aria-required") == "true"
            options = []
            if element.name == "select":
                options = [
                    " ".join(option.get_text(" ", strip=True).split())
                    for option in element.select("option")
                    if option.get_text(" ", strip=True)
                ]

            fields.append({
                "name": str(field_name),
                "type": element.name if element.name != "input" else input_type,
                "required": required,
                "options": options,
            })

        return ExtractionResult(
            state_id=state_id,
            target_id=target_id,
            url=url,
            page_type=page_type,
            strategy="form_schema",
            status="success" if fields else "empty",
            confidence=0.78 if fields else 0.3,
            fields=fields,
            summary={"field_count": len(fields)},
            evidence_paths=evidence_paths,
        )
