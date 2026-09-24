"""The grounded provider: RUMIN's own composer (``composer.py``). No language model."""

from __future__ import annotations

from app.analyst.composer import Composer
from app.analyst.providers.base import ProviderContext, ProviderResult


class GroundedProvider:
    name = "grounded"

    def answer(self, context: ProviderContext) -> ProviderResult:
        draft = Composer(context.route, context.runner, context.vocabulary).compose()
        return ProviderResult(draft=draft)
