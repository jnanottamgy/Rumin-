"""What a conversation is about: its **focus**.

After each turn the session keeps the subject it was about (a company or industry, a
variable, a series, a scenario and execution, the changes of a what-if), so a follow-up
such as "and its revenue exposure?" or "what about 30 %?" can be read. A subject named in a
new question replaces the focus. The focus holds keys only, never results: every turn
fetches its data again.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Focus:
    intent: str | None = None
    subject: str | None = None  # the key "it" refers to: the last turn's main subject
    entity: str | None = None  # company:… or industry:…
    variable: str | None = None  # variable:…
    series: str | None = None  # series:…
    scenario_id: str | None = None
    execution_id: str | None = None
    changes: list[dict[str, str]] = field(default_factory=list)
    horizon: int | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> Focus:
        if not data:
            return cls()

        def text(name: str) -> str | None:
            value = data.get(name)
            return str(value) if value is not None else None

        horizon = data.get("horizon")
        return cls(
            intent=text("intent"),
            subject=text("subject"),
            entity=text("entity"),
            variable=text("variable"),
            series=text("series"),
            scenario_id=text("scenario_id"),
            execution_id=text("execution_id"),
            changes=[
                {str(key): str(value) for key, value in item.items()}
                for item in data.get("changes") or []
                if isinstance(item, dict)
            ],
            horizon=int(horizon) if isinstance(horizon, int) else None,
        )

    def to_json(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value not in (None, [])}

    @property
    def empty(self) -> bool:
        return not self.to_json()


def recent_turns(turns: list[tuple[str, str]], limit: int = 4, width: int = 300) -> list[str]:
    """A bounded summary of the last ``limit`` turns (question and headline), for a language
    model's context. Earlier answers are summarised, never replayed as current data."""
    lines: list[str] = []
    for question, headline in turns[-limit:]:
        lines.append(f"Q: {question[:width]}")
        lines.append(f"A (headline only): {headline[:width]}")
    return lines
