from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMProvider(Protocol):
    provider_name: str
    model: str

    def complete(self, *, system: str, prompt: str, context: dict[str, Any]) -> str: ...


class NullLLMProvider:
    provider_name = "offline"
    model = "none"

    def complete(self, *, system: str, prompt: str, context: dict[str, Any]) -> str:
        return ""


@dataclass(frozen=True)
class OpenAICompatibleLLMProvider:
    """Provider for SiliconFlow, OpenAI, and other /v1/chat/completions APIs."""

    api_keys: tuple[str, ...]
    base_url: str
    model: str
    provider_name: str = "openai-compatible"
    timeout_seconds: float = 90.0
    temperature: float = 0.2
    max_tokens: int = 1800

    def __post_init__(self) -> None:
        if not self.api_keys or not any(self.api_keys):
            raise ValueError("至少需要一个 LLM API Key")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def complete(self, *, system: str, prompt: str, context: dict[str, Any]) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        last_error: Exception | None = None
        for key in self.api_keys:
            if not key:
                continue
            request = Request(
                self.endpoint,
                data=encoded,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "multi-agent-marketing/0.3",
                },
                method="POST",
            )
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    data = json.loads(response.read().decode("utf-8"))
                return self._extract_content(data)
            except HTTPError as exc:
                # Never include response bodies or API keys in logs/errors.
                last_error = RuntimeError(f"LLM HTTP {exc.code}")
                if exc.code not in (401, 403, 408, 409, 429) and exc.code < 500:
                    break
            except (URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError) as exc:
                last_error = exc
        raise RuntimeError(f"{self.provider_name} 调用失败（模型 {self.model}）") from last_error

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("LLM 响应缺少 choices")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        if not isinstance(content, str):
            raise RuntimeError("LLM 响应 content 格式不支持")
        return content.strip()


def build_llm_provider(settings: Any) -> LLMProvider:
    """Build the configured provider; no key means safe deterministic offline mode."""

    provider = str(getattr(settings, "llm_provider", "auto") or "auto").lower()
    if provider in {"none", "offline", "null"}:
        return NullLLMProvider()

    silicon_keys = tuple(
        key
        for key in (
            getattr(settings, "siliconflow_api_key", ""),
            getattr(settings, "siliconflow_api_key_fallback", ""),
        )
        if key
    )
    openai_key = getattr(settings, "openai_api_key", "")
    if provider in {"auto", "siliconflow", "sf"} and silicon_keys:
        return OpenAICompatibleLLMProvider(
            api_keys=silicon_keys,
            base_url=getattr(settings, "siliconflow_base_url", "https://api.siliconflow.cn/v1"),
            model=getattr(settings, "siliconflow_model", "deepseek-ai/DeepSeek-V4-Flash"),
            provider_name="siliconflow",
            timeout_seconds=float(getattr(settings, "llm_timeout_seconds", 90)),
            max_tokens=int(getattr(settings, "llm_max_tokens", 1800)),
        )
    if provider in {"auto", "openai"} and openai_key:
        return OpenAICompatibleLLMProvider(
            api_keys=(openai_key,),
            base_url=getattr(settings, "openai_base_url", "https://api.openai.com/v1"),
            model=getattr(settings, "openai_model", "gpt-5.6-sol"),
            provider_name="openai",
            timeout_seconds=float(getattr(settings, "llm_timeout_seconds", 90)),
            max_tokens=int(getattr(settings, "llm_max_tokens", 1800)),
        )
    if provider not in {"auto", "siliconflow", "sf", "openai"}:
        raise ValueError(f"不支持的 LLM_PROVIDER: {provider}")
    return NullLLMProvider()
