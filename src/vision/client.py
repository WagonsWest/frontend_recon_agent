"""Client abstraction for multimodal page understanding."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image

from src.config import VisionConfig
from src.vision.prompts import build_vision_system_prompt, build_vision_user_prompt
from src.vision.types import DOMSummary, VisionResult


class VisionClient:
    """Thin wrapper around an OpenAI-compatible multimodal API."""

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

        try:
            return await asyncio.to_thread(
                self._request_openai_vision,
                Path(screenshot_path),
                url,
                dom_summary,
                api_key,
            )
        except Exception as e:
            return VisionResult(notes=f"vision_error: {e}")

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

        try:
            return VisionResult.model_validate(parsed)
        except Exception as e:
            return VisionResult(notes=f"vision_parse_error: {e}")

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

    def _prepare_image_bytes(self, screenshot_path: Path) -> bytes:
        """Resize screenshot to configured bounds before upload."""
        with Image.open(screenshot_path) as image:
            max_side = max(1, int(self.config.max_image_side))
            image.thumbnail((max_side, max_side))
            from io import BytesIO
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()
