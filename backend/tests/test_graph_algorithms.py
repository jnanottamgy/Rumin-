"""Graph algorithms: traversal, paths, components and degree — checked against brute force."""

from __future__ import annotations

import random
from collections import deque
from itertools import pairwise

import pytest

from app.graph.algorithms import (
    Direction,
    EdgeFilter,
    Incidence,
    MemoryAdjacency,
    bfs,
    connected_components,
    degrees,
    dfs,
    neighborhood,
    shortest_paths,
)


def edge(
    key: str, source: str, target: str, kind: str = "link", directed: bool = True
) -> Incidence:
    return Incidence(key, kind, source, target, directed)


# a → b → c → d, and a → e; f is isolated; g — h undirected.
LINE = [
    edge("ab", "a", "b"),
    edge("bc", "b", "c"),
    edge("cd", "c", "d"),
    edge("ae", "a", "e", "other"),
    edge("gh", "g", "h", "peer", directed=False),
]
NODES = ["a", "b", "c", "d", "e", "f", "g", "h"]


def test_bfs_visits_by_distance_and_fetches_one_level_per_call() -> None:
    adjacency = MemoryAdjacency(LINE)
    result = bfs(adjacency, "a", max_depth=3, max_nodes=100)
    assert result.depth == {"a": 0, "b": 1, "e": 1, "c": 2, "d": 3}
    assert result.order[0] == "a" and set(result.order[1:3]) == {"b", "e"}
    assert result.parent["d"] == ("c", "cd")
    assert adjacency.calls == 3  # one batched call per level, not one per node


def test_bfs_respects_depth_and_node_budget() -> None:
    assert set(bfs(MemoryAdjacency(LINE), "a", max_depth=1, max_nodes=100).depth) == {"a", "b", "e"}
    capped = bfs(MemoryAdjacency(LINE), "a", max_depth=3, max_nodes=2)
    assert len(capped.order) == 2
    assert capped.truncated and capped.unexplored  # what was cut is reported, not hidden


def test_direction_and_edge_type_filters() -> None:
    adjacency = MemoryAdjacency(LINE)
    backwards = bfs(
        adjacency, "c", max_depth=5, max_nodes=100, edge_filter=EdgeFilter(direction=Direction.IN)
    )
    assert set(backwards.depth) == {"c", "b", "a"}
    forwards = bfs(
        adjacency, "c", max_depth=5, max_nodes=100, edge_filter=EdgeFilter(direction=Direction.OUT)
    )
    assert set(forwards.depth) == {"c", "d"}
    only_links = bfs(
        adjacency,
        "a",
        max_depth=5,
        max_nodes=100,
        edge_filter=EdgeFilter(edge_types=frozenset({"link"})),
    )
    assert "e" not in only_links.depth
    # Undirected edges are followed in both directions whatever the direction filter.
    peers = bfs(
        adjacency, "h", max_depth=1, max_nodes=10, edge_filter=EdgeFilter(direction=Direction.OUT)
    )
    assert set(peers.depth) == {"g", "h"}


def test_node_filter_by_key_prefix() -> None:
    edges = [edge("1", "company:a", "industry:x"), edge("2", "industry:x", "sector:s")]
    only = EdgeFilter(node_filter=lambda key: not key.startswith("sector:"))
    assert set(
        bfs(MemoryAdjacency(edges), "company:a", max_depth=3, max_nodes=10, edge_filter=only).depth
    ) == {
        "company:a",
        "industry:x",
    }


def test_neighborhood_includes_edges_among_the_outermost_nodes() -> None:
    # A triangle hanging off the centre: the x-y edge is only visible from the outer level.
    edges = [edge("cx", "c", "x"), edge("cy", "c", "y"), edge("xy", "x", "y")]
    adjacency = MemoryAdjacency(edges)
    result = neighborhood(adjacency, "c", depth=1, max_nodes=10)
    assert set(result.edges) == {"cx", "cy", "xy"}
    assert adjacency.calls == 2  # depth + 1


def test_dfs_goes_deep_first_without_recursion() -> None:
    chain = [edge(str(i), str(i), str(i + 1)) for i in range(5000)]
    order = dfs(MemoryAdjacency(chain), "0")
    assert order[:4] == ["0", "1", "2", "3"] and len(order) == 5001  # no RecursionError


def test_connected_components() -> None:
    components = connected_components(NODES, MemoryAdjacency(LINE))
    assert components == [["a", "b", "c", "d", "e"], ["g", "h"], ["f"]]


def test_shortest_paths_lists_every_shortest_path_up_to_the_limit() -> None:
    # Two routes of length 2 from s to t, and a longer one.
    edges = [
        edge("s1", "s", "m1"),
        edge("1t", "m1", "t"),
        edge("s2", "s", "m2"),
        edge("2t", "m2", "t"),
        edge("s3", "s", "x"),
        edge("3y", "x", "y"),
        edge("yt", "y", "t"),
    ]
    search = shortest_paths(MemoryAdjacency(edges), "s", "t", max_depth=6, limit=10)
    assert search.length == 2
    assert [path.nodes for path in search.paths] == [("s", "m1", "t"), ("s", "m2", "t")]
    limited = shortest_paths(MemoryAdjacency(edges), "s", "t", max_depth=6, limit=1)
    assert len(limited.paths) == 1


def test_shortest_paths_bounds() -> None:
    adjacency = MemoryAdjacency(LINE)
    assert shortest_paths(adjacency, "a", "d", max_depth=2, limit=1).paths == []  # 3 hops away
    assert shortest_paths(adjacency, "a", "d", max_depth=3, limit=1).length == 3
    assert shortest_paths(adjacency, "a", "f", max_depth=6, limit=1).length is None  # unreachable
    directed = EdgeFilter(direction=Direction.OUT)
    assert (
        shortest_paths(adjacency, "d", "a", max_depth=6, limit=1, edge_filter=directed).length
        is None
    )
    assert (
        shortest_paths(adjacency, "a", "d", max_depth=6, limit=1, edge_filter=directed).length == 3
    )
    same = shortest_paths(adjacency, "a", "a", max_depth=6, limit=1)
    assert same.length == 0 and same.paths[0].nodes == ("a",)


def test_shortest_paths_gives_up_at_the_node_budget() -> None:
    star = [edge(f"h{i}", "hub", f"leaf{i}") for i in range(200)] + [edge("far", "leaf0", "end")]
    search = shortest_paths(
        MemoryAdjacency(star), "leaf5", "nowhere", max_depth=6, limit=1, max_nodes=50
    )
    assert search.budget_exhausted and search.length is None


def test_degrees() -> None:
    result = degrees(NODES, LINE)
    assert result["a"].total == 2 and result["a"].outgoing == 2 and result["a"].incoming == 0
    assert result["g"].total == 1 and result["g"].incoming == result["g"].outgoing == 0
    assert result["f"].total == 0


# --- Cross-checks on random graphs ---------------------------------------------------------------


def random_graph(seed: int, n: int = 30, m: int = 45) -> tuple[list[str], list[Incidence]]:
    rng = random.Random(seed)
    nodes = [f"n{i:02d}" for i in range(n)]
    edges = []
    for index in range(m):
        a, b = rng.sample(nodes, 2)
        edges.append(Incidence(f"e{index:03d}", rng.choice("xyz"), a, b, rng.random() > 0.2))
    return nodes, edges


def brute_distances(
    nodes: list[str], edges: list[Incidence], start: str, rules: EdgeFilter
) -> dict[str, int]:
    adjacency = MemoryAdjacency(edges)
    distance = {start: 0}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for item in adjacency.incident([node])[node]:
            other = rules.follows(item, node)
            if other is not None and other not in distance:
                distance[other] = distance[node] + 1
                queue.append(other)
    return distance


def is_valid_path(
    nodes: tuple[str, ...], edge_keys: tuple[str, ...], edges: list[Incidence], rules: EdgeFilter
) -> bool:
    by_key = {item.edge_key: item for item in edges}
    return all(
        rules.follows(by_key[key], a) == b
        for (a, b), key in zip(pairwise(nodes), edge_keys, strict=True)
    )


@pytest.mark.parametrize("seed", range(25))
@pytest.mark.parametrize("direction", [Direction.ANY, Direction.OUT])
def test_bidirectional_search_matches_brute_force(seed: int, direction: Direction) -> None:
    nodes, edges = random_graph(seed)
    rules = EdgeFilter(direction=direction)
    rng = random.Random(seed * 7)
    for _ in range(10):
        source, target = rng.sample(nodes, 2)
        expected = brute_distances(nodes, edges, source, rules).get(target)
        search = shortest_paths(
            MemoryAdjacency(edges), source, target, max_depth=30, limit=50, edge_filter=rules
        )
        assert search.length == expected
        for path in search.paths:
            assert path.length == expected
            assert path.nodes[0] == source and path.nodes[-1] == target
            assert is_valid_path(path.nodes, path.edges, edges, rules)
        assert len({path.edges for path in search.paths}) == len(search.paths)  # no duplicates


@pytest.mark.parametrize("seed", range(10))
def test_all_shortest_paths_are_found(seed: int) -> None:
    nodes, edges = random_graph(seed, n=14, m=24)
    rules = EdgeFilter()
    source, target = nodes[0], nodes[-1]
    distance = brute_distances(nodes, edges, source, rules).get(target)
    search = shortest_paths(MemoryAdjacency(edges), source, target, max_depth=20, limit=10_000)
    if distance is None:
        assert search.paths == []
        return
    # Count shortest paths (as edge sequences) by dynamic programming over BFS layers.
    adjacency = MemoryAdjacency(edges)
    layers = brute_distances(nodes, edges, source, rules)
    count = {source: 1}
    for node in sorted(layers, key=layers.__getitem__)[1:]:
        count[node] = sum(
            count[item.other(node)]
            for item in adjacency.incident([node])[node]
            if layers.get(item.other(node)) == layers[node] - 1
        )
    assert len(search.paths) == count[target]


@pytest.mark.parametrize("seed", range(10))
def test_bfs_distances_match_brute_force(seed: int) -> None:
    nodes, edges = random_graph(seed)
    rules = EdgeFilter(direction=Direction.OUT)
    result = bfs(
        MemoryAdjacency(edges), nodes[0], max_depth=50, max_nodes=10_000, edge_filter=rules
    )
    assert result.depth == brute_distances(nodes, edges, nodes[0], rules)


@pytest.mark.parametrize("seed", range(10))
def test_components_match_union_find(seed: int) -> None:
    nodes, edges = random_graph(seed, n=40, m=30)
    parent = {node: node for node in nodes}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for item in edges:
        parent[find(item.source)] = find(item.target)
    groups: dict[str, set[str]] = {}
    for node in nodes:
        groups.setdefault(find(node), set()).add(node)
    expected = sorted(
        (sorted(group) for group in groups.values()),
        key=lambda members: (-len(members), members[0]),
    )
    assert connected_components(nodes, MemoryAdjacency(edges)) == expected
