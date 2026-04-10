"""Client abstraction for multimodal page understanding."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from typing import ClassVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image

from src.config import VisionConfig
from src.vision.prompts import (
    build_candidate_ranking_system_prompt,
    build_candidate_ranking_user_prompt,
    build_vision_system_prompt,
    build_vision_user_prompt,
)
from src.vision.types import CandidateRankingResult, DOMSummary, VisionResult


class VisionClient:
    """Thin wrapper around an OpenAI-compatible multimodal API."""

    _request_semaphores: ClassVar[dict[tuple[int, int], asyncio.Semaphore]] = {}

    def __init__(self, config: VisionConfig):
        self.config = config

    async def understand_page(self, screenshot_path: str | Path, url: str,
                              dom_summary: DOMSummary) -> VisionResult:
        """Return a structured page understanding result."""
        if self.config.provider.lower() != "openai":
            return VisionResult(notes=f"unsupported vision provider: {self.config.provider}")

        api_key = self._resolve_api_key()
        if not api_key:
            return VisionResult(notes=f"missing api key in {self.config.api_key_env} or VISION_API_KEY")

        semaphore = self._get_request_semaphore()
        try:
            async with semaphore:
                return await asyncio.to_thread(
                    self._request_openai_vision,
                    Path(screenshot_path),
                    url,
                    dom_summary,
                    api_key,
                )
        except Exception as e:
            return VisionResult(notes=f"vision_error: {e}")

    async def rank_candidates(
        self,
        *,
        kind: str,
        goal: str,
        url: str,
        page_type: str,
        dom_summary: DOMSummary,
        interaction_hints: list[dict] | list | None,
        candidates: list[dict],
    ) -> CandidateRankingResult:
        """Rank visible candidates for the next exploration step."""
        if not candidates:
            return CandidateRankingResult()
        if self.config.provider.lower() != "openai":
            return self._default_candidate_ranking(len(candidates), f"unsupported vision provider: {self.config.provider}")

        api_key = self._resolve_api_key()
        if not api_key:
            return self._default_candidate_ranking(len(candidates), f"missing api key in {self.config.api_key_env} or VISION_API_KEY")

        semaphore = self._get_request_semaphore()
        try:
            async with semaphore:
                return await asyncio.to_thread(
                    self._request_openai_candidate_ranking,
                    kind,
                    goal,
                    url,
                    page_type,
                    dom_summary,
                    interaction_hints or [],
                    candidates,
                    api_key,
                )
        except Exception as e:
            return self._default_candidate_ranking(len(candidates), f"candidate_ranking_error: {e}")

    def _get_request_semaphore(self) -> asyncio.Semaphore:
        limit = max(1, int(self.config.max_concurrent_requests))
        loop_key = id(asyncio.get_running_loop())
        cache_key = (loop_key, limit)
        semaphore = self._request_semaphores.get(cache_key)
        if semaphore is None:
            semaphore = asyncio.Semaphore(limit)
            self._request_semaphores[cache_key] = semaphore
        return semaphore

    def _resolve_api_key(self) -> str:
        """Resolve API key from generic or provider-specific environment variables."""
        return os.environ.get("VISION_API_KEY") or os.environ.get(self.config.api_key_env, "")

    def _request_openai_vision(self, screenshot_path: Path, url: str,
                               dom_summary: DOMSummary, api_key: str) -> VisionResult:
        """Call an OpenAI-compatible chat-completions vision endpoint."""
        image_bytes = self._prepare_image_bytes(screenshot_path)
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        image_url = f"data:image/png;base64,{image_b64}"

        payload = {
            "model": self.config.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": build_vision_system_prompt()},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_vision_user_prompt(url, dom_summary)},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
        }

        endpoint = self._resolve_base_url().rstrip("/") + "/chat/completions"
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.config.timeout_ms / 1000) as response:
                body = response.read().decode("utf-8")
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"http {e.code}: {error_body}") from e
        except URLError as e:
            raise RuntimeError(f"network error: {e}") from e

        raw = json.loads(body)
        content = raw["choices"][0]["message"]["content"]
        parsed = self._parse_content(content)
        normalized = self._normalize_parsed(parsed)

        try:
            return VisionResult.model_validate(normalized)
        except Exception as e:
            return VisionResult(notes=f"vision_parse_error: {e}")

    def _request_openai_candidate_ranking(
        self,
        kind: str,
        goal: str,
        url: str,
        page_type: str,
        dom_summary: DOMSummary,
        interaction_hints: list[dict] | list,
        candidates: list[dict],
        api_key: str,
    ) -> CandidateRankingResult:
        """Call an OpenAI-compatible endpoint to rank next-step candidates."""
        payload = {
            "model": self.config.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": build_candidate_ranking_system_prompt(kind)},
                {
                    "role": "user",
                    "content": build_candidate_ranking_user_prompt(
                        kind=kind,
                        goal=goal,
                        url=url,
                        page_type=page_type,
                        dom_summary=dom_summary,
                        interaction_hints=interaction_hints,
                        candidates=candidates,
                    ),
                },
            ],
        }

        endpoint = self._resolve_base_url().rstrip("/") + "/chat/completions"
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.config.timeout_ms / 1000) as response:
                body = response.read().decode("utf-8")
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"http {e.code}: {error_body}") from e
        except URLError as e:
            raise RuntimeError(f"network error: {e}") from e

        raw = json.loads(body)
        content = raw["choices"][0]["message"]["content"]
        parsed = self._parse_content(content)
        normalized = self._normalize_candidate_ranking(parsed, len(candidates))

        try:
            return CandidateRankingResult.model_validate(normalized)
        except Exception as e:
            return self._default_candidate_ranking(len(candidates), f"candidate_ranking_parse_error: {e}")

    def _resolve_base_url(self) -> str:
        """Resolve base URL from env override or config."""
        return os.environ.get("VISION_API_BASE_URL") or self.config.api_base_url

    def _parse_content(self, content: object) -> dict:
        """Parse JSON content from chat completion output."""
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            text = "\n".join(text_parts).strip()
        else:
            raise ValueError("unexpected vision response content shape")

        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()

        return json.loads(text)

    def _normalize_parsed(self, parsed: dict) -> dict:
        """Normalize loosely structured model output into the expected schema."""
        page_type = self._normalize_page_type(parsed.get("page_type"))
        confidence = self._normalize_confidence(parsed.get("confidence"))
        regions = self._normalize_regions(parsed.get("regions"))
        interaction_hints = self._normalize_interaction_hints(parsed.get("interaction_hints"))
        extraction_hints = self._normalize_extraction_hints(parsed.get("extraction_hints"))
        notes = self._normalize_notes(parsed.get("notes"))
        if not notes and parsed.get("reasoning"):
            notes = self._normalize_notes(parsed.get("reasoning"))

        return {
            "page_type": page_type,
            "confidence": confidence,
            "regions": regions,
            "interaction_hints": interaction_hints,
            "extraction_hints": extraction_hints,
            "notes": notes,
        }

    def _normalize_page_type(self, value: object) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"landing", "content", "docs", "list", "detail", "form", "dashboard", "auth", "modal", "unknown"}:
            return raw

        mappings = {
            "homepage": "landing",
            "home": "landing",
            "marketing": "landing",
            "content": "content",
            "article": "content",
            "community": "content",
            "documentation": "docs",
            "developer docs": "docs",
            "developer portal": "docs",
            "guide": "docs",
            "reference": "docs",
            "auth": "auth",
            "login": "auth",
            "signin": "auth",
            "sign in": "auth",
            "signup": "auth",
            "sign up": "auth",
            "register": "auth",
            "listing": "list",
            "table": "list",
            "search results": "list",
            "record": "detail",
            "profile": "detail",
            "dialog": "modal",
            "drawer": "modal",
        }
        for key, mapped in mappings.items():
            if key in raw:
                return mapped
        return "unknown"

    def _normalize_confidence(self, value: object) -> float:
        try:
            number = float(value)
            return max(0.0, min(1.0, number))
        except Exception:
            return 0.0

    def _normalize_regions(self, value: object) -> list[dict]:
        if isinstance(value, dict):
            items = []
            for key, label in value.items():
                items.append({
                    "region_type": self._normalize_region_type(key),
                    "label": str(label),
                    "bbox_norm": [],
                    "confidence": 0.5,
                })
            return items
        if isinstance(value, list):
            items: list[dict] = []
            for entry in value:
                if isinstance(entry, str):
                    items.append({
                        "region_type": self._normalize_region_type(entry),
                        "label": entry,
                        "bbox_norm": [],
                        "confidence": 0.5,
                    })
                elif isinstance(entry, dict):
                    items.append({
                        "region_type": self._normalize_region_type(entry.get("region_type") or entry.get("type") or entry.get("name")),
                        "label": str(entry.get("label") or entry.get("name") or ""),
                        "bbox_norm": self._normalize_bbox(entry.get("bbox_norm") or entry.get("bbox") or []),
                        "confidence": self._normalize_confidence(entry.get("confidence", 0.5)),
                    })
            return items
        return []

    def _normalize_region_type(self, value: object) -> str:
        raw = str(value or "").strip().lower()
        allowed = {
            "sidebar", "topnav", "filter_bar", "table", "detail_panel", "form",
            "modal", "drawer", "tabs", "pagination", "toolbar", "hero",
            "content", "article", "search_bar", "footer", "unknown",
        }
        if raw in allowed:
            return raw
        mappings = {
            "nav": "topnav",
            "top nav": "topnav",
            "header": "topnav",
            "search": "search_bar",
            "search bar": "search_bar",
            "main content": "content",
            "body": "content",
            "hero": "hero",
            "article": "article",
            "doc": "article",
            "documentation": "article",
        }
        for key, mapped in mappings.items():
            if key in raw:
                return mapped
        return "unknown"

    def _normalize_interaction_hints(self, value: object) -> list[dict]:
        if isinstance(value, dict):
            return [
                {
                    "hint_type": self._normalize_hint_type(key),
                    "target_region": "",
                    "label": str(text),
                    "confidence": 0.5,
                }
                for key, text in value.items()
            ]
        if isinstance(value, list):
            items: list[dict] = []
            for entry in value:
                if isinstance(entry, str):
                    items.append({
                        "hint_type": self._normalize_hint_type(entry),
                        "target_region": "",
                        "label": entry,
                        "confidence": 0.5,
                    })
                elif isinstance(entry, dict):
                    items.append({
                        "hint_type": self._normalize_hint_type(entry.get("hint_type") or entry.get("type") or entry.get("label")),
                        "target_region": str(entry.get("target_region") or ""),
                        "label": str(entry.get("label") or entry.get("text") or ""),
                        "confidence": self._normalize_confidence(entry.get("confidence", 0.5)),
                    })
            return items
        return []

    def _normalize_hint_type(self, value: object) -> str:
        raw = str(value or "").strip().lower()
        allowed = {
            "primary_action", "row_actions", "tab_switch", "open_modal",
            "open_detail", "paginate", "filter", "search", "sign_in",
            "sign_up", "navigate_section", "unknown",
        }
        if raw in allowed:
            return raw
        mappings = {
            "search": "search",
            "sign in": "sign_in",
            "signin": "sign_in",
            "login": "sign_in",
            "sign up": "sign_up",
            "signup": "sign_up",
            "register": "sign_up",
            "navigate": "navigate_section",
            "section": "navigate_section",
            "tab": "tab_switch",
            "modal": "open_modal",
            "detail": "open_detail",
            "pagination": "paginate",
            "filter": "filter",
        }
        for key, mapped in mappings.items():
            if key in raw:
                return mapped
        return "unknown"

    def _normalize_extraction_hints(self, value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [f"{key}: {text}" for key, text in value.items()]
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return []

    def _normalize_notes(self, value: object) -> str:
        if isinstance(value, list):
            return " ".join(str(item) for item in value if str(item).strip())
        if value is None:
            return ""
        return str(value)

    def _normalize_candidate_ranking(self, parsed: dict, candidate_count: int) -> dict:
        notes = self._normalize_notes(parsed.get("notes"))
        choices: list[dict] = []
        seen: set[int] = set()

        raw_choices = parsed.get("choices")
        if isinstance(raw_choices, list):
            for entry in raw_choices:
                if not isinstance(entry, dict):
                    continue
                try:
                    index = int(entry.get("index", -1))
                except Exception:
                    continue
                if index < 0 or index >= candidate_count or index in seen:
                    continue
                seen.add(index)
                choices.append({
                    "index": index,
                    "score": self._normalize_candidate_score(entry.get("score"), candidate_count),
                    "reason": self._normalize_notes(entry.get("reason")),
                })

        raw_indexes = parsed.get("ranked_indexes")
        if not choices and isinstance(raw_indexes, list):
            for position, entry in enumerate(raw_indexes):
                try:
                    index = int(entry)
                except Exception:
                    continue
                if index < 0 or index >= candidate_count or index in seen:
                    continue
                seen.add(index)
                choices.append({
                    "index": index,
                    "score": float(max(candidate_count - position, 1)),
                    "reason": "",
                })

        if not choices:
            return self._default_candidate_ranking(candidate_count, notes).model_dump()

        for index in range(candidate_count):
            if index in seen:
                continue
            choices.append({
                "index": index,
                "score": 0.0,
                "reason": "",
            })

        return {"choices": choices, "notes": notes}

    def _normalize_candidate_score(self, value: object, candidate_count: int) -> float:
        try:
            score = float(value)
        except Exception:
            score = float(candidate_count)
        return max(0.0, min(100.0, score))

    def _default_candidate_ranking(self, candidate_count: int, notes: str = "") -> CandidateRankingResult:
        return CandidateRankingResult(
            choices=[
                {
                    "index": index,
                    "score": float(max(candidate_count - index, 1)),
                    "reason": "fallback_order",
                }
                for index in range(candidate_count)
            ],
            notes=notes,
        )

    def _normalize_bbox(self, value: object) -> list[float]:
        if not isinstance(value, list):
            return []
        numbers: list[float] = []
        for item in value[:4]:
            try:
                numbers.append(float(item))
            except Exception:
                return []
        return numbers

    def _prepare_image_bytes(self, screenshot_path: Path) -> bytes:
        """Resize screenshot to configured bounds before upload."""
        with Image.open(screenshot_path) as image:
            max_side = max(1, int(self.config.max_image_side))
            image.thumbnail((max_side, max_side))
            from io import BytesIO
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()
