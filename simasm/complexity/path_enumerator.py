"""
Enumerate paths through Event Graph for Path-Based HET calculation.
Implements Section 4.4 path enumeration algorithm.

Path-Based HET computes the average complexity across all entity traversal
paths from source to sink vertices.
"""

from typing import List, Set, Dict, Tuple
from .event_graph_parser import EventGraph


def enumerate_paths(
    eg: EventGraph,
    max_cycle_traversals: int = 1
) -> List[List[str]]:
    """
    Enumerate all paths from source to sink vertices.

    For acyclic graphs: enumerate all simple paths.
    For cyclic graphs: allow each cycle to be traversed at most max_cycle_traversals times.

    Args:
        eg: Parsed Event Graph
        max_cycle_traversals: Maximum times a cycle can be traversed (default 1)

    Returns:
        List of paths, where each path is a list of vertex names
    """
    adj = eg.get_adjacency()
    paths = []

    # Find back-edges (cycles)
    back_edges = eg.find_back_edges()

    for source in eg.source_vertices:
        for sink in eg.sink_vertices:
            if source == sink:
                # Source is also sink - single vertex path
                paths.append([source])
                continue

            _dfs_enumerate(
                current=source,
                sink=sink,
                adj=adj,
                path=[source],
                visited=set([source]),
                back_edges=back_edges,
                cycle_counts={e: 0 for e in back_edges},
                max_cycle_traversals=max_cycle_traversals,
                paths=paths
            )

    return paths


def _dfs_enumerate(
    current: str,
    sink: str,
    adj: Dict[str, List[str]],
    path: List[str],
    visited: Set[str],
    back_edges: Set[Tuple[str, str]],
    cycle_counts: Dict[Tuple[str, str], int],
    max_cycle_traversals: int,
    paths: List[List[str]]
):
    """
    DFS helper to enumerate paths with cycle control.

    Args:
        current: Current vertex
        sink: Target sink vertex
        adj: Adjacency list
        path: Current path being built
        visited: Set of visited vertices in current path
        back_edges: Set of back-edges (cycles)
        cycle_counts: Count of cycle traversals
        max_cycle_traversals: Max allowed cycle traversals
        paths: Output list of complete paths
    """
    if current == sink:
        paths.append(path.copy())
        return

    for neighbor in adj.get(current, []):
        edge = (current, neighbor)

        # Check if this is a back-edge
        is_back_edge = edge in back_edges

        if is_back_edge:
            # Check cycle traversal limit
            if cycle_counts[edge] >= max_cycle_traversals:
                continue
            # Allow cycle traversal
            cycle_counts[edge] += 1
            path.append(neighbor)

            # For back-edges, we need to allow revisiting
            # but track that we've used this cycle
            _dfs_enumerate(
                current=neighbor,
                sink=sink,
                adj=adj,
                path=path,
                visited=visited,  # Don't add to visited for back-edge target
                back_edges=back_edges,
                cycle_counts=cycle_counts,
                max_cycle_traversals=max_cycle_traversals,
                paths=paths
            )

            path.pop()
            cycle_counts[edge] -= 1

        elif neighbor not in visited:
            # Normal edge to unvisited vertex
            visited.add(neighbor)
            path.append(neighbor)

            _dfs_enumerate(
                current=neighbor,
                sink=sink,
                adj=adj,
                path=path,
                visited=visited,
                back_edges=back_edges,
                cycle_counts=cycle_counts,
                max_cycle_traversals=max_cycle_traversals,
                paths=paths
            )

            path.pop()
            visited.remove(neighbor)


def calculate_path_het(
    path: List[str],
    event_het: Dict[str, int],
    control_step_cost: int = 20
) -> int:
    """
    Calculate HET for a single path.

    HET_path(p) = sum(HET_event(v) for v in path) + (len(path)-1) * HET_control_step

    Args:
        path: List of vertex names in path
        event_het: Dict mapping vertex name to its HET
        control_step_cost: HET for each control step (default 20 = timing + event_routine)

    Returns:
        Total HET for this path
    """
    if not path:
        return 0

    # Sum event HETs
    event_sum = 0
    for v in path:
        # Try different name variations
        het = event_het.get(v, 0)
        if het == 0:
            # Try lowercase
            het = event_het.get(v.lower(), 0)
        if het == 0:
            # Try with event_ prefix
            het = event_het.get(f'event_{v.lower()}', 0)
        if het == 0:
            # Try capitalized
            het = event_het.get(v.capitalize(), 0)
        event_sum += het

    # Control overhead: (n-1) transitions between events
    control_overhead = (len(path) - 1) * control_step_cost

    return event_sum + control_overhead


def calculate_path_based_het(
    eg: EventGraph,
    event_het: Dict[str, int],
    control_step_cost: int = 20,
    max_cycle_traversals: int = 1
) -> Tuple[float, List[Tuple[List[str], int]]]:
    """
    Calculate Path-Based HET: average HET across all enumerated paths.

    This is the key metric from Section 4.4 that captures execution complexity
    per entity traversal.

    Args:
        eg: Parsed Event Graph
        event_het: Dict mapping vertex/rule name to its HET
        control_step_cost: HET for each control step (default 20)
        max_cycle_traversals: Max cycle traversals for path enumeration

    Returns:
        (average_het, [(path, het), ...]) - Average HET and per-path breakdown
    """
    paths = enumerate_paths(eg, max_cycle_traversals)

    if not paths:
        return 0.0, []

    path_hets = []
    for path in paths:
        het = calculate_path_het(path, event_het, control_step_cost)
        path_hets.append((path, het))

    total_het = sum(het for _, het in path_hets)
    avg_het = total_het / len(path_hets)

    return avg_het, path_hets


def get_path_statistics(
    paths: List[List[str]]
) -> Dict[str, any]:
    """
    Get statistics about enumerated paths.

    Args:
        paths: List of paths

    Returns:
        Dict with path statistics
    """
    if not paths:
        return {
            'num_paths': 0,
            'min_length': 0,
            'max_length': 0,
            'avg_length': 0.0,
        }

    lengths = [len(p) for p in paths]

    return {
        'num_paths': len(paths),
        'min_length': min(lengths),
        'max_length': max(lengths),
        'avg_length': sum(lengths) / len(lengths),
    }
