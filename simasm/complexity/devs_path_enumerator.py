"""
DEVS path enumerator for SMC complexity analysis.

Enumerates source-to-sink paths through the DEVS coupled model graph
and computes path-based SMC metrics.

The coupled model graph is:
  - Nodes = atomic model components
  - Edges = internal couplings (from_model -> to_model)

For each component, the entity cost is:
  HET(d) = HET(internal_transition_d) + HET(external_transition_d) + HET(output_function_d)
"""

import json
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict


class DEVSGraph:
    """Graph representation of a DEVS coupled model for path enumeration."""

    def __init__(self, components: List[str], adjacency: Dict[str, List[str]],
                 sources: List[str], sinks: List[str]):
        self.components = components
        self.adjacency = adjacency  # from_model -> [to_model, ...]
        self.sources = sources  # components with no incoming edges
        self.sinks = sinks  # components with no outgoing edges

    @property
    def V(self) -> int:
        return len(self.components)

    @property
    def E(self) -> int:
        return sum(len(succs) for succs in self.adjacency.values())

    @property
    def edge_density(self) -> float:
        return self.E / (self.V ** 2) if self.V > 0 else 0.0

    @property
    def cyclomatic_number(self) -> int:
        return self.E - self.V + 2

    def has_cycle(self) -> bool:
        """Detect cycles using DFS."""
        visited = set()
        in_stack = set()

        def dfs(node):
            visited.add(node)
            in_stack.add(node)
            for neighbor in self.adjacency.get(node, []):
                if neighbor in in_stack:
                    return True
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
            in_stack.discard(node)
            return False

        for comp in self.components:
            if comp not in visited:
                if dfs(comp):
                    return True
        return False


def parse_devs_graph(json_path: str) -> DEVSGraph:
    """Parse a DEVS JSON specification into a DEVSGraph for path enumeration."""
    with open(json_path, 'r', encoding='utf-8') as f:
        spec = json.load(f)

    coupled = spec["coupled_model"]
    components = coupled["components"]

    # Build adjacency from internal couplings
    adjacency: Dict[str, List[str]] = defaultdict(list)
    incoming: Set[str] = set()

    for coupling in coupled["internal_couplings"]:
        src = coupling["from_model"]
        dst = coupling["to_model"]
        if dst not in adjacency[src]:
            adjacency[src].append(dst)
        incoming.add(dst)

    # Identify sources and sinks
    outgoing = set(adjacency.keys())
    sources = [c for c in components if c not in incoming]
    sinks = [c for c in components if c not in outgoing]

    return DEVSGraph(
        components=components,
        adjacency=dict(adjacency),
        sources=sources,
        sinks=sinks,
    )


def enumerate_devs_paths(graph: DEVSGraph, max_cycle_traversals: int = 0) -> List[List[str]]:
    """Enumerate all source-to-sink paths in the DEVS coupled model graph.

    Args:
        graph: DEVSGraph from parse_devs_graph
        max_cycle_traversals: Max times a cycle can be traversed (0 = acyclic paths only)

    Returns:
        List of paths, where each path is a list of component names.
    """
    all_paths = []

    for source in graph.sources:
        _dfs_paths(graph, source, graph.sinks, [source], set(), all_paths, max_cycle_traversals)

    return all_paths


def _dfs_paths(graph: DEVSGraph, current: str, sinks: List[str],
               path: List[str], visited: Set[str], all_paths: List[List[str]],
               max_cycle_traversals: int):
    """DFS path enumeration."""
    if current in sinks:
        all_paths.append(list(path))
        return

    visited.add(current)

    for neighbor in graph.adjacency.get(current, []):
        visit_count = path.count(neighbor)
        if visit_count <= max_cycle_traversals:
            path.append(neighbor)
            _dfs_paths(graph, neighbor, sinks, path, visited, all_paths, max_cycle_traversals)
            path.pop()

    visited.discard(current)


def compute_devs_smc(graph: DEVSGraph, component_het: Dict[str, int],
                     het_control: int) -> float:
    """Compute path-based SMC for a DEVS model.

    Algorithm:
      1. Enumerate all source-to-sink paths (acyclic)
      2. Collect unique components across all paths
      3. Sum their HET costs
      4. Add control overhead

    Args:
        graph: DEVSGraph from parse_devs_graph
        component_het: Map from component name (lowercase) to combined HET
        het_control: Total HET of control rules

    Returns:
        SMC value
    """
    paths = enumerate_devs_paths(graph, max_cycle_traversals=0)
    if not paths:
        return het_control

    # Collect unique components across all paths
    unique_components = set()
    for p in paths:
        unique_components.update(p)

    # Sum deduplicated component costs
    c_entity = sum(_lookup_component_het(c, component_het) for c in unique_components)

    return c_entity + het_control


def _lookup_component_het(component: str, component_het: Dict[str, int]) -> int:
    """Look up component HET by name, trying multiple formats."""
    for key in [component, component.lower()]:
        if key in component_het:
            return component_het[key]
    return 0


def build_component_het(event_het: Dict[str, int]) -> Dict[str, int]:
    """Build component-level HET from per-rule HET.

    DEVS rules are named:
      - internal_transition_{name}
      - external_transition_{name}
      - output_function_{name}

    Combines all three into a single component HET entry.
    """
    component_het: Dict[str, int] = {}

    for rule_name, het in event_het.items():
        name_lower = rule_name.lower()
        for prefix in ('internal_transition_', 'external_transition_', 'output_function_'):
            if name_lower.startswith(prefix):
                comp_name = name_lower[len(prefix):]
                if comp_name not in component_het:
                    component_het[comp_name] = 0
                component_het[comp_name] += het
                break

    return component_het
