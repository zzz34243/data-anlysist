from __future__ import annotations

from abc import ABC, abstractmethod
import json
import logging
from typing import Any

from ..llm import LLMProvider, NullLLMProvider
from ..memory import MemoryStore

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    name = "base"
    description = ""

    def __init__(self, memory: MemoryStore, llm: LLMProvider | None = None):
        self.memory, self.llm = memory, llm or NullLLMProvider()

    def ask(self, *, system: str, prompt: str, context: dict[str, Any]) -> str:
        """Best-effort enrichment: deterministic pipeline remains usable offline."""
        try:
            return self.llm.complete(system=system, prompt=prompt, context=context).strip()
        except Exception as exc:
            logger.warning("agent=%s LLM enrichment unavailable: %s", self.name, exc)
            return ""

    def ask_json(self, *, system: str, prompt: str, context: dict[str, Any]) -> dict[str, Any] | None:
        text = self.ask(system=system, prompt=prompt, context=context)
        if not text:
            return None
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`").removeprefix("json").strip()
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    @abstractmethod
    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]: ...
