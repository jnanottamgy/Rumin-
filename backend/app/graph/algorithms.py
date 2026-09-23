"""Graph algorithms: bounded traversal, shortest paths, components and degree.

The functions know nothing about databases or HTTP. They see the graph through
``Adjacency.incident(nodes)``, which returns the edges touching a *set* of nodes in one
call. A database-backed adjacency (``app.graph.store``) answers each call with one
indexed query, so a breadth-first search costs one query per level, whatever the number
of nodes on that level ("level-synchronous" traversal). ``MemoryAdjacency`` serves tests
and the build.

The graph is directed and multi-relational: two nodes can be joined by several edges of
different types, and some types (``competes_with``) are undirected. Paths count *hops*:
every edge has length 1. A path shows how records are connected in RUMIN's graph — it is
not an influence, transmission or causal chain.

Complexities are for the explored part of the graph: V nodes and E edges visited.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class Direction(StrEnum):
    """Which way edges may be followed.

    * ``any`` — ignore direction (the graph as undirected).
    * ``out`` — from source to target only (undirected edges both ways).
    * ``in`` — from target to source only (undirected edges both ways).
    """

    ANY = "any"
    OUT = "out"
    IN = "in"

    def reversed(self) -> Direction:
        return {Direction.OUT: Direction.IN, Direction.IN: Direction.OUT}.get(self, self)


@dataclass(frozen=True)
class Incidence:
    """One edge, as seen by the algorithms."""

    edge_key: str
    edge_type: str
    source: str
    target: str
    directed: bool

    def other(self, node: str) -> str:
        return self.target if node == self.source else self.source


class Adjacency(Protocol):
    def incident(self, node_keys: Collection[str]) -> Mapping[str, Sequence[Incidence]]:
        """Every edge touching each of ``node_keys`` (in either direction)."""
        ...


class MemoryAdjacency:
    """An adjacency held in memory (the build, and tests)."""

    def __init__(self, edges: Iterable[Incidence]) -> None:
        self._incident: dict[str, list[Incidence]] = defaultdict(list)
        self.calls = 0  # how many times ``incident`` was asked (tests check batching)
        for edge in edges:
            self._incident[edge.source].append(edge)
            if edge.target != edge.source:
                self._incident[edge.target].append(edge)

    def incident(self, node_keys: Collection[str]) -> Mapping[str, Sequence[Incidence]]:
        self.calls += 1
        return {key: self._incident.get(key, []) for key in node_keys}


@dataclass(frozen=True)
class EdgeFilter:
    """Which edges a traversal may follow, and which nodes it may enter."""

    edge_types: frozenset[str] | None = None
    direction: Direction = Direction.ANY
    # Node keys start with their type ("company:…"), so a node filter needs no lookup.
    node_filter: Callable[[str], bool] | None = None

    def follows(self, edge: Incidence, from_node: str) -> str | None:
        """The neighbour reached from ``from_node`` over ``edge``, or None if not allowed."""
        if self.edge_types is not None and edge.edge_type not in self.edge_types:
            return None
        if edge.directed and self.direction is not Direction.ANY:
            if self.direction is Direction.OUT and edge.source != from_node:
                return None
            if self.direction is Direction.IN and edge.target != from_node:
                return None
        neighbour = edge.other(from_node)
        if self.node_filter is not None and not self.node_filter(neighbour):
            return None
        return neighbour

    def reversed(self) -> EdgeFilter:
        return EdgeFilter(self.edge_types, self.direction.reversed(), self.node_filter)


def _ordered(edges: Iterable[Incidence], node: str) -> list[Incidence]:
    """A deterministic neighbour order, so results never depend on storage order."""
    return sorted(edges, key=lambda edge: (edge.edge_type, edge.other(node), edge.edge_key))


# --- Breadth-first search and neighbourhoods ---------------------------------------------------


@dataclass
class Traversal:
    """The result of a bounded breadth-first search from ``start``."""

    start: str
    order: list[str]
    depth: dict[str, int]
    # How each node was first reached: (parent node, edge key); None for the start.
    parent: dict[str, tuple[str, str] | None]
    edges: dict[str, Incidence]
    # Nodes that were within reach but left out because the node budget was spent.
    unexplored: set[str] = field(default_factory=set)
    levels_fetched: int = 0

    @property
    def truncated(self) -> bool:
        return bool(self.unexplored)


def bfs(
    adjacency: Adjacency,
    start: str,
    *,
    max_depth: int,
    max_nodes: int,
    edge_filter: EdgeFilter | None = None,
) -> Traversal:
    """Breadth-first search, level by level, up to ``max_depth`` hops and ``max_nodes`` nodes.

    Nodes are visited in order of distance (hops) from ``start`` — BFS finds every node's
    shortest hop distance. Time O(V + E), memory O(V), and one ``incident`` call per level.
    Edges between nodes already found are kept too (of the allowed types, in either
    direction). When the node budget runs out, the nodes left out are reported in
    ``unexplored``.
    """
    rules = edge_filter or EdgeFilter()
    result = Traversal(start=start, order=[start], depth={start: 0}, parent={start: None}, edges={})
    frontier = [start]
    for level in range(1, max_depth + 1):
        if not frontier:
            break
        incident = adjacency.incident(frontier)
        result.levels_fetched += 1
        next_frontier: list[str] = []
        for node in frontier:
            for edge in _ordered(incident.get(node, ()), node):
                if rules.edge_types is not None and edge.edge_type not in rules.edge_types:
                    continue
                if edge.other(node) in result.depth:
                    result.edges.setdefault(edge.edge_key, edge)
                    continue
                neighbour = rules.follows(edge, node)
                if neighbour is None:
                    continue
                if len(result.order) >= max_nodes:
                    result.unexplored.add(neighbour)
                    continue
                result.depth[neighbour] = level
                result.parent[neighbour] = (node, edge.edge_key)
                result.order.append(neighbour)
                result.edges[edge.edge_key] = edge
                next_frontier.append(neighbour)
        frontier = next_frontier
    return result


def neighborhood(
    adjacency: Adjacency,
    center: str,
    *,
    depth: int,
    max_nodes: int,
    edge_filter: EdgeFilter | None = None,
) -> Traversal:
    """The nodes within ``depth`` hops of ``center`` and every edge among them.

    A BFS finds the nodes; one more ``incident`` call adds the edges among nodes of the
    outermost level (which the BFS never expanded), so the result is the complete
    subgraph induced by the nodes found. Total cost: ``depth + 1`` calls.
    """
    rules = edge_filter or EdgeFilter()
    result = bfs(adjacency, center, max_depth=depth, max_nodes=max_nodes, edge_filter=rules)
    outer = [node for node in result.order if result.depth[node] == depth]
    if outer and depth > 0:
        incident = adjacency.incident(outer)
        result.levels_fetched += 1
        for node in outer:
            for edge in incident.get(node, ()):
                if rules.edge_types is not None and edge.edge_type not in rules.edge_types:
                    continue
                if edge.other(node) in result.depth:
                    result.edges.setdefault(edge.edge_key, edge)
    return result


# --- Depth-first search and connected components -----------------------------------------------


def dfs(
    adjacency: Adjacency,
    start: str,
    *,
    edge_filter: EdgeFilter | None = None,
    max_nodes: int | None = None,
) -> list[str]:
    """Iterative depth-first search; returns nodes in the order first visited (preorder).

    An explicit stack instead of recursion, so deep graphs cannot exhaust Python's call
    stack. DFS goes as deep as possible before backtracking: useful for reachability and
    components, where the order does not matter, but — unlike BFS — it says nothing about
    distances. Time O(V + E), memory O(V). One ``incident`` call per node: use it on an
    in-memory adjacency.
    """
    rules = edge_filter or EdgeFilter()
    seen = {start}
    order = [start]
    stack: list[Iterator[Incidence]] = [iter(_ordered(adjacency.incident([start])[start], start))]
    path = [start]
    while stack:
        try:
            edge = next(stack[-1])
        except StopIteration:
            stack.pop()
            path.pop()
            continue
        neighbour = rules.follows(edge, path[-1])
        if neighbour is None or neighbour in seen:
            continue
        if max_nodes is not None and len(order) >= max_nodes:
            break
        seen.add(neighbour)
        order.append(neighbour)
        path.append(neighbour)
        stack.append(iter(_ordered(adjacency.incident([neighbour])[neighbour], neighbour)))
    return order


def connected_components(nodes: Iterable[str], adjacency: Adjacency) -> list[list[str]]:
    """Weakly connected components: groups of nodes linked by edges, direction ignored.

    Each unvisited node starts a DFS that collects its component. Time O(V + E). Returned
    largest first (ties: by smallest node key); each component sorted by key. A component
    is a set of records reachable from each other in RUMIN's data — not an economically
    integrated system.
    """
    remaining = sorted(set(nodes))
    assigned: set[str] = set()
    components: list[list[str]] = []
    for node in remaining:
        if node in assigned:
            continue
        members = dfs(adjacency, node)
        assigned.update(members)
        components.append(sorted(members))
    components.sort(key=lambda members: (-len(members), members[0]))
    return components


# --- Shortest paths ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Path:
    nodes: tuple[str, ...]
    edges: tuple[str, ...]

    @property
    def length(self) -> int:
        return len(self.edges)


@dataclass
class PathSearch:
    paths: list[Path]
    # Hops of the shortest path; None when no path was found.
    length: int | None
    nodes_explored: int
    # True when the search stopped at its node budget before it could decide.
    budget_exhausted: bool = False
    levels_fetched: int = 0


@dataclass
class _Side:
    """One half of a bidirectional search."""

    rules: EdgeFilter
    distance: dict[str, int]
    # Every shortest-path predecessor of each node: (previous node, edge key).
    previous: dict[str, list[tuple[str, str]]]
    frontier: list[str]
    depth: int = 0

    def expand(self, adjacency: Adjacency) -> None:
        incident = adjacency.incident(self.frontier)
        next_frontier: list[str] = []
        for node in self.frontier:
            for edge in _ordered(incident.get(node, ()), node):
                neighbour = self.rules.follows(edge, node)
                if neighbour is None:
                    continue
                known = self.distance.get(neighbour)
                if known is None:
                    self.distance[neighbour] = self.depth + 1
                    self.previous[neighbour] = []
                    next_frontier.append(neighbour)
                elif known != self.depth + 1:
                    continue
                self.previous[neighbour].append((node, edge.edge_key))
        self.depth += 1
        self.frontier = next_frontier


def shortest_paths(
    adjacency: Adjacency,
    source: str,
    target: str,
    *,
    max_depth: int,
    limit: int,
    edge_filter: EdgeFilter | None = None,
    max_nodes: int = 5_000,
) -> PathSearch:
    """Up to ``limit`` shortest paths (fewest hops) from ``source`` to ``target``.

    **Bidirectional BFS**: one search grows from each end, always expanding the smaller
    frontier, until they meet. With branching factor b and distance d this explores about
    2·b^(d/2) nodes instead of b^d. When they first meet after levels ``a`` (forward) and
    ``b`` (backward), every path of length ≤ a + b passes through a node both searches
    reached, so the shortest length is the smallest ``forward + backward`` distance over
    the nodes in both, and every shortest path is a shortest prefix to such a node joined
    to a shortest suffix from it. Each search keeps *all* shortest predecessors, so every
    shortest path can be listed; ties are broken by node and edge keys (deterministic).

    Bounded: at most ``max_depth`` hops, and the search gives up (``budget_exhausted``)
    after reaching ``max_nodes`` nodes.
    """
    rules = edge_filter or EdgeFilter()
    if source == target:
        return PathSearch([Path((source,), ())], 0, 1)
    forward = _Side(rules, {source: 0}, {source: []}, [source])
    backward = _Side(rules.reversed(), {target: 0}, {target: []}, [target])
    levels = 0
    while forward.frontier and backward.frontier and forward.depth + backward.depth < max_depth:
        side = forward if len(forward.frontier) <= len(backward.frontier) else backward
        side.expand(adjacency)
        levels += 1
        meeting = forward.distance.keys() & backward.distance.keys()
        if meeting:
            return _collect(forward, backward, meeting, limit, levels)
        if len(forward.distance) + len(backward.distance) > max_nodes:
            return PathSearch(
                [], None, len(forward.distance) + len(backward.distance), True, levels
            )
    return PathSearch([], None, len(forward.distance) + len(backward.distance), False, levels)


def _collect(
    forward: _Side, backward: _Side, meeting: set[str], limit: int, levels: int
) -> PathSearch:
    best = min(forward.distance[node] + backward.distance[node] for node in meeting)
    joints = sorted(
        node for node in meeting if forward.distance[node] + backward.distance[node] == best
    )
    found: dict[tuple[str, ...], Path] = {}
    for joint in joints:
        for head_nodes, head_edges in _walk(forward.previous, joint):
            for tail_nodes, tail_edges in _walk(backward.previous, joint):
                nodes = (*reversed(head_nodes), *tail_nodes[1:])
                edges = (*reversed(head_edges), *tail_edges)
                found.setdefault(edges, Path(nodes, edges))
                if len(found) >= limit:
                    return _search_result(found, best, forward, backward, levels)
    return _search_result(found, best, forward, backward, levels)


def _search_result(
    found: dict[tuple[str, ...], Path], best: int, forward: _Side, backward: _Side, levels: int
) -> PathSearch:
    paths = sorted(found.values(), key=lambda path: (path.nodes, path.edges))
    return PathSearch(paths, best, len(forward.distance) + len(backward.distance), False, levels)


def _walk(
    previous: dict[str, list[tuple[str, str]]], node: str
) -> Iterator[tuple[list[str], list[str]]]:
    """Every shortest route from ``node`` back to the search's start, as (nodes, edges),
    starting at ``node``. Iterative, lazily generated (there can be very many)."""
    stack: list[tuple[str, list[str], list[str]]] = [(node, [node], [])]
    while stack:
        current, nodes, edges = stack.pop()
        steps = previous.get(current, [])
        if not steps:
            yield nodes, edges
            continue
        for before, edge in sorted(steps, reverse=True):
            stack.append((before, [*nodes, before], [*edges, edge]))


# --- Degree ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Degree:
    total: int
    incoming: int
    outgoing: int


def degrees(nodes: Iterable[str], edges: Iterable[Incidence]) -> dict[str, Degree]:
    """Edges touching each node. For directed edges, ``incoming``/``outgoing`` by direction;
    an undirected edge counts once in ``total`` and in neither direction."""
    total: dict[str, int] = defaultdict(int)
    incoming: dict[str, int] = defaultdict(int)
    outgoing: dict[str, int] = defaultdict(int)
    for edge in edges:
        total[edge.source] += 1
        total[edge.target] += 1
        if edge.directed:
            outgoing[edge.source] += 1
            incoming[edge.target] += 1
    return {node: Degree(total[node], incoming[node], outgoing[node]) for node in nodes}
