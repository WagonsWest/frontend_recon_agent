"""List/table extractor."""

from __future__ import annotations

from bs4 import BeautifulSoup

from src.extraction.types import EvidencePaths, ExtractionResult


class ListExtractor:
    """Extracts table headers and first rows from list-like pages."""

    def extract(self, html: str, state_id: str, target_id: str, url: str,
                page_type: str, evidence_paths: EvidencePaths,
                max_rows: int = 10) -> ExtractionResult:
        soup = BeautifulSoup(html, "lxml")

        table = soup.select_one("table, .el-table table, .ant-table table")
        if not table:
            return ExtractionResult(
                state_id=state_id,
                target_id=target_id,
                url=url,
                page_type=page_type,
                strategy="list_table",
                status="empty",
                evidence_paths=evidence_paths,
                summary={"reason": "no table found"},
            )

        headers = [
            " ".join(th.get_text(" ", strip=True).split())
            for th in table.select("thead th")
            if th.get_text(" ", strip=True)
        ]
        if not headers:
            first_row = table.select_one("tr")
            if first_row:
                cell_count = len(first_row.select("td, th"))
                headers = [f"column_{i + 1}" for i in range(cell_count)]

        records: list[dict[str, str]] = []
        for row in table.select("tbody tr")[:max_rows]:
            cells = [
                " ".join(td.get_text(" ", strip=True).split())
                for td in row.select("td, th")
            ]
            if not any(cells):
                continue
            row_obj = {}
            for idx, cell in enumerate(cells):
                key = headers[idx] if idx < len(headers) else f"column_{idx + 1}"
                row_obj[key] = cell
            records.append(row_obj)

        if not records and table.select("tr"):
            for row in table.select("tr")[1:max_rows + 1]:
                cells = [
                    " ".join(td.get_text(" ", strip=True).split())
                    for td in row.select("td, th")
                ]
                if not any(cells):
                    continue
                row_obj = {}
                for idx, cell in enumerate(cells):
                    key = headers[idx] if idx < len(headers) else f"column_{idx + 1}"
                    row_obj[key] = cell
                records.append(row_obj)

        return ExtractionResult(
            state_id=state_id,
            target_id=target_id,
            url=url,
            page_type=page_type,
            strategy="list_table",
            status="success" if records or headers else "empty",
            confidence=0.8 if records else 0.45,
            records=records,
            summary={
                "header_count": len(headers),
                "row_count": len(records),
                "headers": headers,
            },
            evidence_paths=evidence_paths,
        )
