"""
Parse Event Graph structure from JSON specification.
Extracts vertices, edges, and graph properties for complexity analysis.

Based on Section 4 of the HET Complexity Metric paper.
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional
from pathlib import Path


@dataclass
class Vertex:
    """Event Graph vertex (event)."""
    name: str
    state_change: str = ""
    parameters: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class Edge:
    """Event Graph scheduling edge."""
    from_vertex: str
    to_vertex: str
    delay: str = "0"
    condition: str = "true"
    priority: int = 0
    parameters: List[str] = field(default_factory=list)


@dataclass
class EventGraph:
    """Parsed Event Graph structure."""
    name: str
    vertices: List[Vertex]
    scheduling_edges: List[Edge]
    cancelling_edges: List[Edge]
    initial_events: List[str]

    # Derived properties
    source_vertices: List[str] = field(default_factory=list)  # Entry points (e.g., Arrive)
    sink_vertices: List[str] = field(default_factory=list)    # Exit points (e.g., Depart, Finish_N)

    @property
    def V(self) -> int:
        """Vertex count |V|."""
        return len(self.vertices)

    @property
    def E(self) -> int:
        """Edge count |E| (scheduling edges only)."""
        return len(self.scheduling_edges)

    @property
    def vertex_count(self) -> int:
        """Alias for V."""
        return self.V

    @property
    def edge_count(self) -> int:
        """Alias for E."""
        return self.E

    @property
    def edge_density(self) -> float:
        """Edge density |E| / |V|^2."""
        return self.E / (self.V ** 2) if self.V > 0 else 0.0

    @property
    def cyclomatic_number(self) -> int:
        """Cyclomatic number |E| - |V| + 2p (p=1 for connected graph)."""
        return self.E - self.V + 2

    def get_adjacency(self) -> Dict[str, List[str]]:
        """Get adjacency list representation."""
        adj = {v.name: [] for v in self.vertices}
        for e in self.scheduling_edges:
            if e.from_vertex in adj:
                adj[e.from_vertex].append(e.to_vertex)
        return adj

    def get_vertex_names(self) -> Set[str]:
        """Get set of all vertex names."""
        return {v.name for v in self.vertices}

    def has_cycle(self) -> bool:
        """Check if graph has cycles using DFS."""
        adj = self.get_adjacency()
        visited = set()
        rec_stack = set()

        def dfs(v: str) -> bool:
            visited.add(v)
            rec_stack.add(v)
            for neighbor in adj.get(v, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(v)
            return False

        for v in adj:
            if v not in visited:
                if dfs(v):
                    return True
        return False

    def find_back_edges(self) -> Set[Tuple[str, str]]:
        """Find all back-edges that create cycles (graph-theoretic)."""
        adj = self.get_adjacency()
        back_edges = set()
        visited = set()
        rec_stack = set()

        def dfs(v: str):
            visited.add(v)
            rec_stack.add(v)

            for neighbor in adj.get(v, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # Found back-edge
                    back_edges.add((v, neighbor))

            rec_stack.remove(v)

        for v in adj:
            if v not in visited:
                dfs(v)

        return back_edges

    def find_entity_feedback_edges(self) -> Set[Tuple[str, str]]:
        """Find back-edges that represent entity feedback loops.

        Filters out:
        - Self-loops (generator edges like Arrive -> Arrive)
        - Server-scheduling edges (parameter starts with 'next_',
          e.g. Finish_1 -> Start_1 with next_load)

        Only retains edges where the same entity cycles back through
        the system (e.g. Rework -> Start, Readmit -> Triage).
        """
        all_back_edges = self.find_back_edges()

        # Build a lookup: (from, to) -> edge parameters
        edge_params = {}
        for e in self.scheduling_edges:
            key = (e.from_vertex, e.to_vertex)
            if key not in edge_params:
                edge_params[key] = e.parameters

        entity_feedback = set()
        for (u, v) in all_back_edges:
            # Skip self-loops (generator edges)
            if u == v:
                continue
            # Skip server-scheduling edges (next_* parameter)
            params = edge_params.get((u, v), [])
            if any(str(p).startswith("next_") for p in params):
                continue
            entity_feedback.add((u, v))

        return entity_feedback


def parse_event_graph(json_path: str) -> EventGraph:
    """
    Parse Event Graph from JSON specification.

    Args:
        json_path: Path to Event Graph JSON file

    Returns:
        EventGraph object with parsed structure
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        spec = json.load(f)

    # Parse vertices
    vertices = []
    for v_spec in spec.get('vertices', []):
        params = []
        if 'parameters' in v_spec:
            for p in v_spec['parameters']:
                if isinstance(p, dict):
                    params.extend(p.keys())
                else:
                    params.append(str(p))

        vertices.append(Vertex(
            name=v_spec['name'],
            state_change=v_spec.get('state_change', ''),
            parameters=params,
            description=v_spec.get('description', '')
        ))

    # Parse scheduling edges
    scheduling_edges = []
    for e_spec in spec.get('scheduling_edges', []):
        scheduling_edges.append(Edge(
            from_vertex=e_spec['from'],
            to_vertex=e_spec['to'],
            delay=str(e_spec.get('delay', 0)),
            condition=e_spec.get('condition', 'true'),
            priority=e_spec.get('priority', 0),
            parameters=e_spec.get('parameters', [])
        ))

    # Parse cancelling edges
    cancelling_edges = []
    for e_spec in spec.get('cancelling_edges', []):
        cancelling_edges.append(Edge(
            from_vertex=e_spec['from'],
            to_vertex=e_spec['to'],
            condition=e_spec.get('condition', 'true')
        ))

    # Parse initial events
    initial_events = []
    for ie in spec.get('initial_events', []):
        initial_events.append(ie['event'])

    # Create graph
    eg = EventGraph(
        name=spec.get('model_name', 'unnamed'),
        vertices=vertices,
        scheduling_edges=scheduling_edges,
        cancelling_edges=cancelling_edges,
        initial_events=initial_events
    )

    # Identify source vertices (have initial events or no incoming edges)
    incoming = {v.name: 0 for v in vertices}
    for e in scheduling_edges:
        if e.to_vertex in incoming:
            incoming[e.to_vertex] += 1

    eg.source_vertices = initial_events.copy()
    for v in vertices:
        if incoming[v.name] == 0 and v.name not in eg.source_vertices:
            eg.source_vertices.append(v.name)

    # Identify sink vertices (no outgoing edges or specific naming patterns)
    outgoing = {v.name: 0 for v in vertices}
    for e in scheduling_edges:
        if e.from_vertex in outgoing:
            outgoing[e.from_vertex] += 1

    # Find vertices with no outgoing edges
    for v in vertices:
        if outgoing[v.name] == 0:
            eg.sink_vertices.append(v.name)

    # Also check for "Depart" named vertices
    for v in vertices:
        if v.name.lower() == 'depart' and v.name not in eg.sink_vertices:
            eg.sink_vertices.append(v.name)

    # For tandem/feedback queues, the last Finish_N is typically a sink
    # even if it has self-loop edges
    if not eg.sink_vertices:
        finish_vertices = [v.name for v in vertices if v.name.lower().startswith('finish')]
        if finish_vertices:
            # Get highest numbered finish
            try:
                sorted_finish = sorted(finish_vertices,
                                      key=lambda x: int(x.split('_')[-1]) if '_' in x else 0,
                                      reverse=True)
                eg.sink_vertices = [sorted_finish[0]]
            except (ValueError, IndexError):
                eg.sink_vertices = [finish_vertices[-1]]

    return eg


def parse_event_graph_from_dict(spec: Dict) -> EventGraph:
    """
    Parse Event Graph from dictionary specification.

    Args:
        spec: Event Graph specification dictionary

    Returns:
        EventGraph object with parsed structure
    """
    # Parse vertices
    vertices = []
    for v_spec in spec.get('vertices', []):
        params = []
        if 'parameters' in v_spec:
            for p in v_spec['parameters']:
                if isinstance(p, dict):
                    params.extend(p.keys())
                else:
                    params.append(str(p))

        vertices.append(Vertex(
            name=v_spec['name'],
            state_change=v_spec.get('state_change', ''),
            parameters=params,
            description=v_spec.get('description', '')
        ))

    # Parse scheduling edges
    scheduling_edges = []
    for e_spec in spec.get('scheduling_edges', []):
        scheduling_edges.append(Edge(
            from_vertex=e_spec['from'],
            to_vertex=e_spec['to'],
            delay=str(e_spec.get('delay', 0)),
            condition=e_spec.get('condition', 'true'),
            priority=e_spec.get('priority', 0),
            parameters=e_spec.get('parameters', [])
        ))

    # Parse cancelling edges
    cancelling_edges = []
    for e_spec in spec.get('cancelling_edges', []):
        cancelling_edges.append(Edge(
            from_vertex=e_spec['from'],
            to_vertex=e_spec['to'],
            condition=e_spec.get('condition', 'true')
        ))

    # Parse initial events
    initial_events = []
    for ie in spec.get('initial_events', []):
        initial_events.append(ie['event'])

    # Create and return graph (without source/sink identification for simplicity)
    eg = EventGraph(
        name=spec.get('model_name', 'unnamed'),
        vertices=vertices,
        scheduling_edges=scheduling_edges,
        cancelling_edges=cancelling_edges,
        initial_events=initial_events,
        source_vertices=initial_events.copy(),
        sink_vertices=[]
    )

    return eg
