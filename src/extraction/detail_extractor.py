"""Detail/key-value extractor."""

from __future__ import annotations

from bs4 import BeautifulSoup

from src.extraction.types import EvidencePaths, ExtractionResult


class DetailExtractor:
    """Extracts detail fields from description and label-value layouts."""

    def extract(self, html: str, state_id: str, target_id: str, url: str,
                page_type: str, evidence_paths: EvidencePaths) -> ExtractionResult:
        soup = BeautifulSoup(html, "lxml")
        fields: list[dict[str, str]] = []

        for item in soup.select(".el-descriptions-item, .ant-descriptions-item")[:30]:
            label_node = item.select_one(
                ".el-descriptions__label, .ant-descriptions-item-label, dt, label"
            )
            value_node = item.select_one(
                ".el-descriptions__content, .ant-descriptions-item-content, dd, .value"
            )
            label = " ".join(label_node.get_text(" ", strip=True).split()) if label_node else ""
            value = " ".join(value_node.get_text(" ", strip=True).split()) if value_node else ""
            if label and value:
                fields.append({"label": label, "value": value})

        if not fields:
            candidates = soup.select(
                ".detail-item, .info-item, .form-item, .el-form-item, .ant-form-item"
            )
            for item in candidates[:30]:
                label_node = item.select_one(
                    ".label, .name, .el-form-item__label, .ant-form-item-label label, label"
                )
                value_node = item.select_one(
                    ".value, .content, .el-form-item__content, .ant-form-item-control-input, span, div"
                )
                label = " ".join(label_node.get_text(" ", strip=True).split()) if label_node else ""
                value = " ".join(value_node.get_text(" ", strip=True).split()) if value_node else ""
                if label and value and label != value:
                    fields.append({"label": label, "value": value})

        return ExtractionResult(
            state_id=state_id,
            target_id=target_id,
            url=url,
            page_type=page_type,
            strategy="detail_fields",
            status="success" if fields else "empty",
            confidence=0.75 if fields else 0.35,
            fields=fields,
            summary={"field_count": len(fields)},
            evidence_paths=evidence_paths,
        )
