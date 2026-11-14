from __future__ import annotations

import json
import os
import re
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Any

import httpx

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

class RateLimiter:

    def __init__(self, max_calls: int = 5, period_s: float = 60.0) -> None:
        self.max_calls = max(1, int(max_calls))
        self.period_s = float(period_s)
        self._times: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._times and now - self._times[0] >= self.period_s:
                    self._times.popleft()
                if len(self._times) < self.max_calls:
                    self._times.append(now)
                    return
                sleep_for = self.period_s - (now - self._times[0]) + 0.05
            time.sleep(max(sleep_for, 0.05))

_RATE_LIMITER: RateLimiter | None = None
_RATE_LOCK = threading.Lock()

def get_rate_limiter(max_rpm: int | None = None) -> RateLimiter:
    global _RATE_LIMITER
    with _RATE_LOCK:
        if _RATE_LIMITER is None or (max_rpm is not None and _RATE_LIMITER.max_calls != max_rpm):
            rpm = max_rpm if max_rpm is not None else int(os.getenv("LLM_MAX_RPM", "5"))
            _RATE_LIMITER = RateLimiter(max_calls=rpm)
        return _RATE_LIMITER

def resolve_http_proxy() -> str | None:
    for key in ("LLM_HTTP_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        value = os.getenv(key, "").strip()
        if value:
            return value
    return None

@dataclass
class LLMConfig:
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "bonsai-2:27b"
    api_key: str = ""
    timeout_s: float = 900.0
    temperature: float = 0.2
    num_ctx: int = 8192
    keep_alive: str = "30m"
    reasoning_effort: str = "low"
    max_rpm: int = 5
    max_retries: int = 2
    max_tokens: int = 2048
    http_proxy: str | None = None

    @classmethod
    def from_env(cls) -> LLMConfig:
        provider = os.getenv("LLM_PROVIDER", cls.provider).strip().lower()
        if provider in {"gemini", "google"}:
            default_base = "https://generativelanguage.googleapis.com"
            default_model = "gemini-4-hydrogen"
            default_key = os.getenv("GEMINI_API_KEY", "")
            default_timeout = 600.0
            default_effort = "high"
        elif provider in {"openai", "cloud"}:
            default_base = "https://api.openai.com"
            default_model = "gpt-6.1-sol"
            default_key = os.getenv("OPENAI_API_KEY", os.getenv("LLM_API_KEY", ""))
            default_timeout = 600.0
            default_effort = "high"
        elif provider == "openrouter":
            default_base = "https://openrouter.ai/api"
            default_model = "baidu/ernie-5.5-flash-preview:free"
            default_key = os.getenv("OPENROUTER_API_KEY", os.getenv("LLM_API_KEY", ""))
            default_timeout = 90.0
            default_effort = "low"
        else:
            default_base = "http://127.0.0.1:11434"
            default_model = "bonsai-2:27b"
            default_key = ""
            default_timeout = 900.0
            default_effort = "low"
        return cls(
            provider=provider,
            base_url=os.getenv("LLM_BASE_URL", default_base).rstrip("/"),
            model=os.getenv("LLM_MODEL", default_model),
            api_key=default_key,
            timeout_s=float(os.getenv("LLM_TIMEOUT_S", default_timeout)),
            temperature=float(os.getenv("LLM_TEMPERATURE", cls.temperature)),
            num_ctx=int(os.getenv("LLM_NUM_CTX", cls.num_ctx)),
            keep_alive=os.getenv("LLM_KEEP_ALIVE", cls.keep_alive),
            reasoning_effort=os.getenv("LLM_REASONING_EFFORT", default_effort),
            max_rpm=int(os.getenv("LLM_MAX_RPM", cls.max_rpm)),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", cls.max_retries)),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", cls.max_tokens)),
            http_proxy=None if provider in {"ollama", "local"} else resolve_http_proxy(),
        )

def _ollama_think(effort: str) -> bool | str:
    e = (effort or "").strip().lower()
    if e in {"", "none", "off", "false", "0", "no"}:
        return False
    if e in {"true", "on", "1", "yes"}:
        return True
    if e in {"low", "medium", "high", "max"}:
        return e
    return False

def strip_think(text: str) -> str:
    return _THINK_RE.sub("", text or "").strip()

def extract_json_object(text: str | None) -> dict[str, Any]:
    if text is None:
        raise ValueError("LLM returned empty content")
    cleaned = strip_think(text).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()
    if not cleaned:
        raise ValueError("LLM returned empty content")

    candidates: list[str] = []
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        candidates.append(cleaned[start : end + 1])
    last = cleaned.rfind('{"mapping"')
    if last < 0:
        last = cleaned.rfind('{"atom_mapping"')
    if last >= 0:
        end2 = cleaned.find("}", last)
        end2 = cleaned.rfind("}")
        if end2 > last:
            candidates.append(cleaned[last : end2 + 1])
    candidates.append(cleaned)

    last_err: Exception | None = None
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except Exception as exc:
            last_err = exc
            continue
    match = re.search(r'"mapping"\s*:\s*(\[[^\]]+\])', cleaned)
    if match:
        return {"mapping": json.loads(match.group(1))}
    match = re.search(r'"mapping"\s*:\s*(\{[^{}]+\})', cleaned)
    if match:
        return {"mapping": json.loads(match.group(1))}
    preview = ascii(cleaned[:180])
    raise ValueError(f"LLM returned non-JSON content: {preview}") from last_err

def _coerce_mapping(mapping: Any) -> list[int]:
    if isinstance(mapping, list) and mapping:
        return [int(x) for x in mapping]
    if isinstance(mapping, dict) and mapping:
        items = [(int(k), int(v)) for k, v in mapping.items()]
        n = max(i for i, _ in items) + 1
        out = [-1] * n
        for i, j in items:
            out[i] = j
        if any(x < 0 for x in out):
            raise ValueError(f"incomplete mapping dict: {mapping}")
        return out
    raise ValueError(f"LLM JSON missing mapping list; got {type(mapping).__name__}")

def normalize_mapping_answer(answer: dict[str, Any]) -> dict[str, Any]:
    out = dict(answer)
    if "mapping" not in out:
        for alt in ("atom_mapping", "map", "permutation"):
            if alt in out:
                out["mapping"] = out[alt]
                break
    out["mapping"] = _coerce_mapping(out.get("mapping"))
    bc = out.get("bond_changes")
    if not isinstance(bc, dict):
        out["bond_changes"] = {"broken": [], "formed": []}
    else:
        out["bond_changes"] = {
            "broken": bc.get("broken") or [],
            "formed": bc.get("formed") or [],
        }
    if "confidence" not in out:
        out["confidence"] = 0.5
    if "reasoning_steps" not in out or not isinstance(out["reasoning_steps"], list):
        out["reasoning_steps"] = []
    return out

def _message_content(message: dict[str, Any]) -> str | None:
    content = message.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                parts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                parts.append(item)
        content = "\n".join(parts)
    blobs: list[str] = []
    if isinstance(content, str) and content.strip():
        blobs.append(content.strip())
    for key in ("reasoning", "refusal"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            blobs.append(value.strip())
    if not blobs:
        return None
    for blob in blobs:
        if re.search(r'[{[]\s*"mapping"', blob) or re.search(r'"mapping"\s*:', blob):
            return blob
    for blob in blobs:
        if "{" in blob:
            return blob
    return blobs[0]

def _choice_meta(data: dict[str, Any]) -> tuple[str | None, str | None]:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    finish = choice.get("finish_reason") or choice.get("native_finish_reason")
    return _message_content(message), str(finish) if finish is not None else None

def _choice_text(data: dict[str, Any]) -> str:
    content, finish = _choice_meta(data)
    if content:
        return content
    raise ValueError(
        f"LLM returned no content (finish_reason={finish}). "
        "Lower LLM_REASONING_EFFORT or raise LLM_MAX_TOKENS."
    )

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mapping": {"type": "array", "items": {"type": "integer"}},
        "confidence": {"type": "number"},
        "reasoning_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["mapping"],
}

def _strip_unsupported_schema_keys(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            k: _strip_unsupported_schema_keys(v)
            for k, v in node.items()
            if k not in {"additionalProperties", "additional_properties"}
        }
    if isinstance(node, list):
        return [_strip_unsupported_schema_keys(x) for x in node]
    return node

def _http_error_detail(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
        err = payload.get("error", payload)
        if isinstance(err, dict):
            msg = err.get("message") or err.get("status") or str(err)
            detail = f"{resp.status_code} {msg}"
        else:
            detail = f"{resp.status_code} {err}"
    except Exception:
        detail = f"{resp.status_code} {resp.text[:500]}"

    low = detail.lower()
    if resp.status_code == 403 and "security policy" in low:
        return (
            f"{detail} — OpenRouter/Cloudflare блокирует этот IP/регион "
            "(это не ключ и не модель). Нужен VPN/прокси (LLM_HTTP_PROXY), "
            "либо локальный Ollama (LLM_PROVIDER=ollama)."
        )
    if resp.status_code == 429 and "free-models-per-day" in low:
        return (
            "OpenRouter: дневной лимит бесплатных моделей исчерпан "
            "(обычно 50/день). Подожди сброса, пополни credits "
            "(+$10 → 1000 free/день), или поставь платную модель."
        )
    if resp.status_code == 429:
        return f"OpenRouter rate limit: {detail}"
    return detail

class LLMProvider(ABC):
    @abstractmethod
    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

def _http_client(timeout_s: float, proxy: str | None = None) -> httpx.Client:
    kwargs: dict[str, Any] = {"timeout": timeout_s, "trust_env": bool(proxy)}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.Client(**kwargs)

def _post_json(
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout_s: float,
    max_rpm: int,
    proxy: str | None = None,
) -> httpx.Response:
    get_rate_limiter(max_rpm).wait()
    with _http_client(timeout_s, proxy=proxy) as client:
        return client.post(url, json=body, headers=headers)

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
        attempts = max(2, self.config.max_retries)
        for attempt in range(attempts):
            think = False if attempt > 0 else _ollama_think(self.config.reasoning_effort)
            body = {
                "model": self.config.model,
                "messages": payload_messages,
                "stream": False,
                "keep_alive": self.config.keep_alive,
                "format": schema,
                "think": think,
                "options": {
                    "temperature": 0.2 if attempt == 0 else 0.0,
                    "num_ctx": self.config.num_ctx,
                    "num_predict": self.config.max_tokens,
                },
            }
            try:
                get_rate_limiter(self.config.max_rpm).wait()
                with _http_client(self.config.timeout_s, proxy=None) as client:
                    resp = client.post(f"{self.config.base_url}/api/chat", json=body)
                    if resp.status_code >= 400:
                        raise RuntimeError(_http_error_detail(resp))
                    data = resp.json()
                msg = data.get("message") or {}
                content = msg.get("content") or ""
                thinking = msg.get("thinking") or ""
                text = content if str(content).strip() else thinking
                if not str(text).strip():
                    raise ValueError("Ollama returned empty content")
                return normalize_mapping_answer(extract_json_object(str(text)))
            except Exception as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                payload_messages = [
                    {
                        "role": "system",
                        "content": 'Reply with only {"mapping":[...]} as a JSON object.',
                    },
                    messages[-1],
                    {
                        "role": "user",
                        "content": (
                            f"Previous reply failed ({exc}). "
                            'Output only {"mapping":[0,1,...]} with a valid permutation.'
                        ),
                    },
                ]
        assert last_error is not None
        raise last_error

class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        if not self.config.api_key:
            if self.config.provider == "openrouter":
                raise ValueError("Set OPENROUTER_API_KEY in .env")
            raise ValueError("Set LLM_API_KEY (or OPENAI_API_KEY) for cloud provider")

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del schema
        last_error: Exception | None = None
        payload_messages = list(messages)
        base = self.config.base_url
        url = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
        attempts = 3
        is_free = self.config.model.lower().endswith(":free")
        max_tokens = min(max(self.config.max_tokens, 2048), 4096 if is_free else self.config.max_tokens)
        last_raw_text = ""

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(attempts):
            body: dict[str, Any] = {
                "model": self.config.model,
                "messages": payload_messages,
                "stream": False,
                "max_tokens": 384 if attempt else max_tokens,
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
            }
            if not is_free:
                body["reasoning"] = {"effort": "low", "exclude": True}

            try:
                resp = _post_json(
                    url,
                    headers=headers,
                    body=body,
                    timeout_s=min(self.config.timeout_s, 90.0),
                    max_rpm=self.config.max_rpm,
                    proxy=self.config.http_proxy,
                )
                if resp.status_code >= 400 and "reasoning" in body:
                    body.pop("reasoning", None)
                    resp = _post_json(
                        url,
                        headers=headers,
                        body=body,
                        timeout_s=min(self.config.timeout_s, 90.0),
                        max_rpm=self.config.max_rpm,
                        proxy=self.config.http_proxy,
                    )
                if resp.status_code >= 400:
                    body.pop("response_format", None)
                    resp = _post_json(
                        url,
                        headers=headers,
                        body=body,
                        timeout_s=min(self.config.timeout_s, 90.0),
                        max_rpm=self.config.max_rpm,
                        proxy=self.config.http_proxy,
                    )
                if resp.status_code >= 400:
                    raise RuntimeError(_http_error_detail(resp))
                data = resp.json()
                content, finish = _choice_meta(data)
                if content:
                    last_raw_text = content
                if not content:
                    raise ValueError(f"LLM returned no content (finish_reason={finish})")
                try:
                    return normalize_mapping_answer(extract_json_object(content))
                except Exception as parse_exc:
                    raise ValueError(
                        f"invalid LLM JSON (finish_reason={finish}): {parse_exc}"
                    ) from parse_exc
            except Exception as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                notes = (last_raw_text or "")[:1800]
                payload_messages = [
                    {
                        "role": "system",
                        "content": (
                            'Output ONLY one JSON object. First char must be "{". '
                            'Shape: {"mapping":[integers...]}. No analysis text.'
                        ),
                    },
                    messages[-1],
                    {
                        "role": "user",
                        "content": (
                            "Convert your analysis into the final mapping JSON now.\n"
                            f"Notes so far:\n{notes}\n"
                            'Reply with only {"mapping":[...]}'
                        ),
                    },
                ]
        assert last_error is not None
        raise last_error

class GeminiProvider(LLMProvider):
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        if not self.config.api_key:
            raise ValueError("Set GEMINI_API_KEY in .env")

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        schema = _strip_unsupported_schema_keys(schema or RESPONSE_SCHEMA)
        system = ""
        contents: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                system = text if not system else f"{system}\n\n{text}"
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": text}]})

        thinking = self.config.reasoning_effort.strip().lower()
        if thinking in {"none", "minimal"}:
            thinking = "low"
        if thinking not in {"low", "medium", "high", "xhigh"}:
            thinking = "high"

        url = f"{self.config.base_url}/v1beta/models/{self.config.model}:generateContent"
        headers = {
            "x-goog-api-key": self.config.api_key,
            "Content-Type": "application/json",
        }
        attempts = max(1, self.config.max_retries)
        last_error: Exception | None = None

        for attempt in range(attempts):
            generation_config: dict[str, Any] = {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                "maxOutputTokens": self.config.max_tokens,
                "thinkingConfig": {"thinkingLevel": thinking},
            }
            body: dict[str, Any] = {
                "contents": contents,
                "generationConfig": generation_config,
            }
            if system:
                body["system_instruction"] = {"parts": [{"text": system}]}

            try:
                resp = _post_json(
                    url,
                    headers=headers,
                    body=body,
                    timeout_s=self.config.timeout_s,
                    max_rpm=self.config.max_rpm,
                    proxy=self.config.http_proxy,
                )
                if resp.status_code >= 400:
                    detail = _http_error_detail(resp)
                    if "location is not supported" in detail.lower():
                        raise RuntimeError(
                            f"Gemini API blocked for this region ({detail}). "
                            "Set LLM_HTTP_PROXY to Happ local proxy (e.g. http://127.0.0.1:10809), "
                            "or use OpenRouter with the same proxy."
                        )
                    raise RuntimeError(detail)
                data = resp.json()
                parts = data["candidates"][0]["content"]["parts"]
                text_parts = [p.get("text", "") for p in parts if "text" in p]
                content = "\n".join(text_parts).strip()
                return extract_json_object(content)
            except RuntimeError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                contents = list(contents) + [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": f"Previous answer was invalid JSON ({exc}). Reply with valid JSON only."
                            }
                        ],
                    }
                ]
        assert last_error is not None
        raise last_error

def make_llm_provider(config: LLMConfig | None = None) -> LLMProvider:
    cfg = config or LLMConfig.from_env()
    if cfg.provider in {"gemini", "google"}:
        return GeminiProvider(cfg)
    if cfg.provider in {"openai", "openrouter", "cloud"}:
        return OpenAICompatibleProvider(cfg)
    return OllamaProvider(cfg)
