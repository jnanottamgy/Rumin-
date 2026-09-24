"""Helpers the tools share: evidence for graph records, paths for display, thresholds."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from app.analyst.answer import PathItem, PathLink, PathStep
from app.analyst.evidence import Knowledge, SourceRef, node_link
from app.analyst.policy import data_text
from app.analyst.tools.registry import RenderContext
from app.intelligence.thresholds import DEFAULTS, Thresholds
from app.schemas.intelligence import EdgeInfoRead, ExposurePathRead, NodeRead


def counted(count: int, one: str, many: str | None = None) -> str:
    """'1 path', '4 paths': a count with its noun, for tool summaries."""
    return f"{count} {one if count == 1 else (many or one + 's')}"


THRESHOLDS: Thresholds = DEFAULTS
KIND_LABEL = {
    "company": "company",
    "industry": "industry",
    "economic_variable": "economic variable",
    "data_series": "data series",
    "country": "country",
    "currency": "currency",
    "sector": "sector",
    "instrument": "instrument",
    "market": "market",
}
STATUS_LABEL = {
    "evidence_backed": "evidence-backed",
    "analyst_created": "analyst-created",
    "model_assumption": "a model assumption",
    "unverified": "unverified",
}


def edge_link(source: str, target: str) -> str:
    """The Graph Explorer's path view between an edge's two ends (it shows the edge)."""
    from urllib.parse import urlencode

    return f"/graph?{urlencode({'from': source, 'to': target})}"


def node_ref(node: NodeRead) -> SourceRef:
    return SourceRef(kind="graph_node", id=node.key, label=node.name, link=node_link(node.key))


def node_evidence(
    ctx: RenderContext,
    tool: str,
    node: NodeRead,
    read_at: datetime,
    build_id: int | None,
    detail: str | None = None,
) -> str:
    attributes = {
        key: str(value)
        for key, value in node.attributes.items()
        if isinstance(value, str | int) and key in ("unit", "frequency", "category", "code")
    }
    fictional = node.nature == "fictional"
    return ctx.ledger.add(
        tool=tool,
        call=ctx.call,
        kind=Knowledge.RECORD,
        title=f"{node.name} ({KIND_LABEL.get(node.node_type, node.node_type)})",
        detail=data_text(detail)
        if detail
        else ("A fictional company of RUMIN's illustrative sample network." if fictional else None),
        source=node_ref(node),
        retrieved_at=read_at,
        as_of=f"graph build {build_id}" if build_id else None,
        provenance={
            "graph_build": str(build_id) if build_id else None,
            "nature": node.nature,
            **attributes,
        },
    )


def edge_evidence(
    ctx: RenderContext,
    tool: str,
    edge: EdgeInfoRead,
    names: dict[str, str],
    read_at: datetime,
    build_id: int | None,
) -> str:
    source = names.get(edge.source, edge.source)
    target = names.get(edge.target, edge.target)
    detail = " ".join(
        part
        for part in (
            data_text(edge.rationale or edge.description, 400),
            f"What it does not mean: {data_text(edge.caveat, 300)}" if edge.caveat else None,
            "Illustrative: it involves the fictional sample network."
            if edge.is_illustrative
            else None,
        )
        if part
    )
    return ctx.ledger.add(
        tool=tool,
        call=ctx.call,
        kind=Knowledge.RELATIONSHIP,
        title=f"{source} — {edge.label} → {target}",
        detail=detail,
        source=SourceRef(
            kind="graph_edge",
            id=edge.key,
            label=f"{source} {edge.label} {target}",
            link=edge_link(edge.source, edge.target),
        ),
        retrieved_at=read_at,
        as_of=f"graph build {build_id}" if build_id else None,
        evidence_status=edge.evidence_status,
        provenance={
            "graph_build": str(build_id) if build_id else None,
            "polarity": edge.polarity,
            "strength": edge.strength,
            "evidence_level": edge.evidence_level,
        },
    )


def path_names(paths: Iterable[ExposurePathRead], entity: NodeRead | None = None) -> dict[str, str]:
    names: dict[str, str] = {}
    if entity is not None:
        names[entity.key] = entity.name
    for path in paths:
        for node in (path.origin, path.variable, *path.hops):
            names[node.key] = node.name
        if path.industry is not None:
            names[path.industry.key] = path.industry.name
    return names


def path_item(
    ctx: RenderContext,
    tool: str,
    path: ExposurePathRead,
    entity: NodeRead,
    names: dict[str, str],
    read_at: datetime,
    build_id: int | None,
) -> PathItem:
    """One exposure path for display, with each relationship recorded as evidence."""
    steps = [
        PathStep(key=node.key, name=node.name, kind=node.node_type, link=node_link(node.key))
        for node in path.hops
    ]
    if path.industry is not None:
        steps.append(
            PathStep(
                key=path.industry.key,
                name=path.industry.name,
                kind=path.industry.node_type,
                link=node_link(path.industry.key),
            )
        )
    steps.append(
        PathStep(
            key=entity.key, name=entity.name, kind=entity.node_type, link=node_link(entity.key)
        )
    )
    citations = [edge_evidence(ctx, tool, edge, names, read_at, build_id) for edge in path.edges]
    return PathItem(
        steps=steps,
        links=[
            PathLink(
                key=edge.key,
                label=edge.label,
                evidence_status=edge.evidence_status,
                illustrative=edge.is_illustrative,
            )
            for edge in path.edges
        ],
        channel=path.channel,
        directness=path.directness,
        evidence_status=path.evidence_status,
        models=list(path.models),
        citations=citations,
    )


def compact_path(path: ExposurePathRead) -> dict[str, Any]:
    """A path as a language model sees it."""
    return {
        "from": path.origin.name,
        "variable": path.variable.name,
        "variable_key": path.variable.key,
        "channel": path.channel,
        "how": path.directness,
        "industry": path.industry.name if path.industry else None,
        "relationships": [edge.label for edge in path.edges],
        "weakest_evidence": path.evidence_status,
        "models": list(path.models),
    }


def bounded(items: Sequence[Any], limit: int) -> tuple[list[Any], int]:
    return list(items[:limit]), len(items)
