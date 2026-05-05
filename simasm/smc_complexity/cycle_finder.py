"""
DFS fundamental cycle detection on the scheduling subgraph.

Implements the algorithm from the SMC draft:
- DFS from source vertex (or all roots for disconnected graphs)
- Back edges define fundamental cycles
- Each cycle = (vertices_in_order, edges_in_order)
"""

from typing import List, Tuple

from .models import SchedulingEdge, SchedulingSubgraph, CycleInfo


UNVISITED = 0
VISITING = 1
VISITED = 2


def find_fundamental_cycles(
    graph: SchedulingSubgraph,
    c_step: int,
    event_het: dict,
) -> List[CycleInfo]:
    """
    Find fundamental cycles via DFS and compute their cost/period/rate.

    Each back edge produces one fundamental cycle. Self-loops are
    single-vertex cycles.

    Raises ValueError if any cycle has zero period (all edges immediate).
    """
    if not graph.vertices:
        return []

    status = {v: UNVISITED for v in graph.vertices}
    parent = {v: None for v in graph.vertices}
    parent_edge = {v: None for v in graph.vertices}
    raw_cycles: List[Tuple[List[str], List[SchedulingEdge]]] = []

    def dfs(v: str):
        status[v] = VISITING
        for edge in graph.adjacency.get(v, []):
            w = edge.to_vertex
            if status.get(w, UNVISITED) == UNVISITED:
                parent[w] = v
                parent_edge[w] = edge
                dfs(w)
            elif status.get(w) == VISITING:
                cycle_verts = []
                cycle_edges = []
                if v == w:
                    cycle_verts = [w]
                    cycle_edges = [edge]
                else:
                    x = v
                    while x != w:
                        cycle_verts.insert(0, x)
                        cycle_edges.insert(0, parent_edge[x])
                        x = parent[x]
                    cycle_verts.insert(0, w)
                    cycle_edges.append(edge)
                raw_cycles.append((cycle_verts, cycle_edges))
        status[v] = VISITED

    dfs(graph.source_vertex)

    cycles = _build_cycle_infos(raw_cycles, c_step, event_het)
    return cycles


def find_fundamental_cycles_multi_root(
    graph: SchedulingSubgraph,
    c_step: int,
    event_het: dict,
) -> List[CycleInfo]:
    """
    Find fundamental cycles via DFS from all unvisited vertices.

    Unlike find_fundamental_cycles() which starts only from source_vertex,
    this iterates over all vertices so cycles in disconnected scheduling
    subgraphs (e.g. warehouse with 4 arrival sources) are found.

    Skips zero-period cycles (all-immediate edges) instead of raising.
    """
    if not graph.vertices:
        return []

    status = {v: UNVISITED for v in graph.vertices}
    parent = {v: None for v in graph.vertices}
    parent_edge = {v: None for v in graph.vertices}
    raw_cycles: List[Tuple[List[str], List[SchedulingEdge]]] = []

    def dfs(v: str):
        status[v] = VISITING
        for edge in graph.adjacency.get(v, []):
            w = edge.to_vertex
            if status.get(w, UNVISITED) == UNVISITED:
                parent[w] = v
                parent_edge[w] = edge
                dfs(w)
            elif status.get(w) == VISITING:
                cycle_verts = []
                cycle_edges = []
                if v == w:
                    cycle_verts = [w]
                    cycle_edges = [edge]
                else:
                    x = v
                    while x != w:
                        cycle_verts.insert(0, x)
                        cycle_edges.insert(0, parent_edge[x])
                        x = parent[x]
                    cycle_verts.insert(0, w)
                    cycle_edges.append(edge)
                raw_cycles.append((cycle_verts, cycle_edges))
        status[v] = VISITED

    for v in sorted(graph.vertices):
        if status[v] == UNVISITED:
            dfs(v)

    cycles = _build_cycle_infos(raw_cycles, c_step, event_het, skip_zero_period=True)
    return cycles


def _build_cycle_infos(
    raw_cycles: List[Tuple[List[str], List[SchedulingEdge]]],
    c_step: int,
    event_het: dict,
    skip_zero_period: bool = False,
) -> List[CycleInfo]:
    cycles = []
    for idx, (verts, edges) in enumerate(raw_cycles):
        cost = sum(c_step + _lookup_het(v, event_het) for v in verts)
        period = sum(e.mean_delay for e in edges)
        if period <= 0:
            if skip_zero_period:
                continue
            zero_verts = " -> ".join(verts)
            raise ValueError(
                f"Cycle c{idx+1} [{zero_verts}] has zero period. "
                f"Every cycle must contain at least one positive-delay edge "
                f"(Zeigler's legitimate model condition)."
            )
        rate = cost / period
        cycles.append(CycleInfo(
            index=len(cycles) + 1,
            vertices=verts,
            edges=edges,
            cost=cost,
            period=period,
            rate=rate,
        ))
    return cycles


def _normalize(s: str) -> str:
    """Normalize to lowercase, collapse multi-underscores, strip event_ prefix."""
    import re
    s = s.lower()
    s = re.sub(r'_+', '_', s)
    if s.startswith("event_"):
        s = s[6:]
    return s


def _lookup_het(vertex_name: str, event_het: dict) -> int:
    """Look up HET for an event vertex, trying name variants."""
    for name in [
        vertex_name,
        vertex_name.lower(),
        f"event_{vertex_name.lower()}",
        vertex_name.replace(" ", "_").lower(),
    ]:
        if name in event_het:
            return event_het[name]

    norm = _normalize(vertex_name)
    for key, cost in event_het.items():
        if _normalize(key) == norm:
            return cost

    raise KeyError(
        f"No HET cost found for event '{vertex_name}'. "
        f"Available: {list(event_het.keys())}"
    )
