"""A scripted stand-in for the language model, for tests.

``ScriptedClient`` answers ``messages.create`` with the next of a list of scripted
responses, built as the SDK's own ``Message`` objects, and records every request it was
sent. Used with ``AnthropicProvider(client=ScriptedClient(...))``, it exercises exactly the
loop a real model would — tool calls through the registry, invalid calls, invented figures,
refusals, cut-off answers — without a network. It is never configured in the application.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from anthropic.types import Message

Step = dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]


def tool_use(name: str, arguments: dict[str, Any], *, index: int = 1) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"toolu_{index:04d}", "name": name, "input": arguments}


def reply(
    *blocks: dict[str, Any], stop_reason: str | None = None, model: str = "scripted-model"
) -> dict[str, Any]:
    """A response made of ``blocks`` (the stop reason follows from them unless given)."""
    uses = any(block.get("type") == "tool_use" for block in blocks)
    return {
        "id": "msg_scripted",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": list(blocks),
        "stop_reason": stop_reason or ("tool_use" if uses else "end_turn"),
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def submit(
    headline: str,
    *paragraphs: tuple[str, str],
    status: str = "answered",
    show: Sequence[int] = (),
    follow_ups: Sequence[str] = (),
) -> dict[str, Any]:
    return reply(
        tool_use(
            "submit_answer",
            {
                "status": status,
                "headline": headline,
                "paragraphs": [{"role": role, "text": body} for role, body in paragraphs],
                "show": list(show),
                "follow_ups": list(follow_ups),
            },
            index=999,
        )
    )


@dataclass
class _Messages:
    owner: ScriptedClient

    def create(self, **params: Any) -> Message:
        self.owner.requests.append(params)
        if not self.owner.steps:
            raise AssertionError("The scripted model has no more responses.")
        step = self.owner.steps.pop(0)
        data = step(params) if callable(step) else step
        return Message.model_validate(data)


@dataclass
class ScriptedClient:
    steps: list[Step]
    requests: list[dict[str, Any]] = field(default_factory=list)

    @property
    def messages(self) -> _Messages:
        return _Messages(self)
