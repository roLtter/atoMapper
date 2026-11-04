from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass
class LLMConfig:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "neb-fast"
    timeout_s: float = 600.0
    temperature: float = 0.2
    num_ctx: int = 8192
    keep_alive: str = "2m"

    @classmethod
    def from_env(cls) -> LLMConfig:
        return cls(
            base_url=os.getenv("LLM_BASE_URL", cls.base_url).rstrip("/"),
            model=os.getenv("LLM_MODEL", cls.model),
            timeout_s=float(os.getenv("LLM_TIMEOUT_S", cls.timeout_s)),
            temperature=float(os.getenv("LLM_TEMPERATURE", cls.temperature)),
            num_ctx=int(os.getenv("LLM_NUM_CTX", cls.num_ctx)),
            keep_alive=os.getenv("LLM_KEEP_ALIVE", cls.keep_alive),
        )


def strip_think(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = strip_think(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chosen_candidate": {"type": "integer"},
        "mapping": {"type": "array", "items": {"type": "integer"}},
        "bond_changes": {
            "type": "object",
            "properties": {
                "broken": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
                "formed": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
            },
            "required": ["broken", "formed"],
        },
        "confidence": {"type": "number"},
        "reasoning_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["chosen_candidate", "mapping", "bond_changes", "confidence", "reasoning_steps"],
}


class LLMProvider(ABC):
    @abstractmethod
    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        schema = schema or RESPONSE_SCHEMA
        last_error: Exception | None = None
        payload_messages = list(messages)
        for attempt in range(3):
            body = {
                "model": self.config.model,
                "messages": payload_messages,
                "stream": False,
                "keep_alive": self.config.keep_alive,
                "format": schema,
                "options": {
                    "temperature": self.config.temperature,
                    "num_ctx": self.config.num_ctx,
                },
            }
            try:
                with httpx.Client(timeout=self.config.timeout_s) as client:
                    resp = client.post(f"{self.config.base_url}/api/chat", json=body)
                    resp.raise_for_status()
                    data = resp.json()
                content = data.get("message", {}).get("content", "")
                return extract_json_object(content)
            except Exception as exc:
                last_error = exc
                payload_messages = list(messages) + [
                    {
                        "role": "user",
                        "content": f"Previous answer was invalid JSON ({exc}). Reply with valid JSON only.",
                    }
                ]
        assert last_error is not None
        raise last_error
