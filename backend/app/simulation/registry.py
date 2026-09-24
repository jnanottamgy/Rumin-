"""The versioned model registry: which models exist, in which versions.

A model version is its definition plus two functions (``check`` and ``compute``). Old
versions stay registered for as long as their runs should remain re-executable; a
deprecated version is still readable but not offered for new runs.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property

from app.simulation.definitions import ModelDefinition, ModelStatus, definition_hash
from app.simulation.models import (
    airline_fuel_cost,
    airline_fuel_cost_1_1,
    commodity_linked_costs,
    floating_rate_interest,
    fx_exposure,
)
from app.simulation.runtime import CheckFunction, ComputeFunction

# The engine's own version: recorded with every run, part of its inputs hash.
ENGINE_VERSION = "1.0.0"


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


@dataclass(frozen=True)
class RegisteredModel:
    definition: ModelDefinition
    check: CheckFunction
    compute: ComputeFunction

    @cached_property
    def definition_hash(self) -> str:
        return definition_hash(self.definition)

    @property
    def runnable(self) -> bool:
        return self.definition.status is not ModelStatus.DEPRECATED


class ModelRegistry:
    def __init__(self, models: Iterable[RegisteredModel]) -> None:
        self._models: dict[tuple[str, str], RegisteredModel] = {}
        for model in models:
            key = (model.definition.id, model.definition.version)
            if key in self._models:
                raise ValueError(f"Model {key} is registered twice.")
            self._models[key] = model

    def get(self, model_id: str, version: str | None = None) -> RegisteredModel | None:
        """A model version, or the latest runnable version when ``version`` is None."""
        if version is not None:
            return self._models.get((model_id, version))
        candidates = [model for model in self.versions(model_id) if model.runnable]
        return candidates[0] if candidates else None

    def versions(self, model_id: str) -> list[RegisteredModel]:
        """Every registered version of a model, newest first."""
        return sorted(
            (model for (identifier, _), model in self._models.items() if identifier == model_id),
            key=lambda model: version_key(model.definition.version),
            reverse=True,
        )

    def latest(self) -> list[RegisteredModel]:
        """The newest version of each model, ordered by model id."""
        ids = sorted({identifier for identifier, _ in self._models})
        return [self.versions(identifier)[0] for identifier in ids]


REGISTRY = ModelRegistry(
    [
        # 1.0.0 stays registered unchanged so that its runs remain re-executable.
        RegisteredModel(
            definition=airline_fuel_cost.DEFINITION,
            check=airline_fuel_cost.check,
            compute=airline_fuel_cost.compute,
        ),
        RegisteredModel(
            definition=airline_fuel_cost_1_1.DEFINITION,
            check=airline_fuel_cost_1_1.check,
            compute=airline_fuel_cost_1_1.compute,
        ),
        RegisteredModel(
            definition=fx_exposure.DEFINITION,
            check=fx_exposure.check,
            compute=fx_exposure.compute,
        ),
        RegisteredModel(
            definition=floating_rate_interest.DEFINITION,
            check=floating_rate_interest.check,
            compute=floating_rate_interest.compute,
        ),
        RegisteredModel(
            definition=commodity_linked_costs.CRUDE_DEFINITION,
            check=commodity_linked_costs.crude_check,
            compute=commodity_linked_costs.crude_compute,
        ),
        RegisteredModel(
            definition=commodity_linked_costs.GAS_DEFINITION,
            check=commodity_linked_costs.gas_check,
            compute=commodity_linked_costs.gas_compute,
        ),
    ]
)
