"""What every provider receives and returns.

A provider composes the answer to one question. It gets the routed question, the tool
runner (the only way to data), the vocabulary and the conversation's focus and recent
turns; it returns a draft answer. The orchestrator checks the draft against the evidence
the runner recorded, whatever the provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.analyst.composer import Draft
from app.analyst.context import Focus
from app.analyst.router import Route
from app.analyst.tools.registry import ToolRunner
from app.analyst.vocabulary import Vocabulary


@dataclass
class ProviderContext:
    route: Route
    runner: ToolRunner
    vocabulary: Vocabulary
    focus: Focus
    history: list[tuple[str, str]] = field(default_factory=list)  # (question, headline)


@dataclass
class Usage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def to_json(self) -> dict[str, int]:
        return {
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


class ProviderFailed(Exception):
    """The provider could not produce a draft; ``reason`` is safe to store and show."""

    def __init__(self, reason: str, *, usage: Usage | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.usage = usage or Usage()


@dataclass
class ProviderResult:
    draft: Draft
    usage: Usage = field(default_factory=Usage)
    model: str | None = None
    notes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    name: str

    def answer(self, context: ProviderContext) -> ProviderResult: ...
