"""
Enumerate entity paths through Activity Cycle Diagram for path-based SMC.

Builds the activity graph from queue-mediated produce/consume relationships
in the ACD JSON specification. Entity paths track job/token flow through
non-resource queues, ignoring resource returns.

Mirrors the EG path_enumerator.py approach:
  1. Parse ACD JSON -> activity graph (activities as nodes, queue connections as edges)
  2. Identify source activities (those that create new entity tokens)
  3. Identify sink activities (those that produce to terminal queues)
  4. Remove back-edges (feedback cycles)
  5. Enumerate all acyclic source-to-sink paths
  6. Deduplicate activities across paths
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional
from pathlib import Path


@dataclass
class ACDActivity:
    """ACD activity node."""
    name: str
    priority: int = 0
    consumes_from: List[str] = field(default_factory=list)   # non-resource queues consumed
    produces_to: List[str] = field(default_factory=list)     # non-resource queues produced to (entity flow)
    resource_consumes: List[str] = field(default_factory=list)  # resource queues consumed
    resource_produces: List[str] = field(default_factory=list)  # resource queues returned to
    creates_new_tokens: bool = False  # has token_source="new" to non-resource queue


@dataclass
class ACDGraph:
    """Parsed ACD activity graph."""
    name: str
    activities: List[ACDActivity]
    queues: Dict[str, bool]  # queue_name -> is_resource
    adjacency: Dict[str, List[str]]  # activity -> [successor activities]

    source_activities: List[str] = field(default_factory=list)
    sink_activities: List[str] = field(default_factory=list)
    sink_queues: Set[str] = field(default_factory=set)

    def get_activity_names(self) -> Set[str]:
        return {a.name for a in self.activities}

    def has_cycle(self) -> bool:
        visited = set()
        rec_stack = set()

        def dfs(v):
            visited.add(v)
            rec_stack.add(v)
            for neighbor in self.adjacency.get(v, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(v)
            return False

        for v in self.adjacency:
            if v not in visited:
                if dfs(v):
                    return True
        return False

    def find_back_edges(self) -> Set[Tuple[str, str]]:
        """Find all back-edges that create cycles via DFS."""
        back_edges = set()
        visited = set()
        rec_stack = set()

        def dfs(v):
            visited.add(v)
            rec_stack.add(v)
            for neighbor in self.adjacency.get(v, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    back_edges.add((v, neighbor))
            rec_stack.remove(v)

        for v in self.adjacency:
            if v not in visited:
                dfs(v)

        return back_edges


def parse_acd_graph(json_path: str) -> ACDGraph:
    """
    Parse ACD JSON specification into an activity graph.

    Builds adjacency from queue-mediated connections:
      Activity A produces entity tokens to queue Q  ->
      Activity B consumes from queue Q  ->
      Edge: A -> B

    Resource queues (is_resource=true) are filtered out to avoid
    resource-return edges (e.g., server token cycling back).

    Args:
        json_path: Path to ACD JSON specification file

    Returns:
        ACDGraph with activities, adjacency, sources, and sinks
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        spec = json.load(f)

    # Parse queues: identify which are resource queues
    queues = {}
    for q_name, q_spec in spec.get('queues', {}).items():
        queues[q_name] = q_spec.get('is_resource', False)

    # Parse activities
    activities = []
    # Track which non-resource queues each activity consumes from
    queue_consumers: Dict[str, List[str]] = {}  # queue -> [activity names that consume from it]

    for act_spec in spec.get('activities', []):
        act_name = act_spec['name']

        consumes_from = []
        resource_consumes = []
        produces_to = []
        resource_produces = []
        creates_new = False

        # Parse at_begin consume
        at_begin = act_spec.get('at_begin', {})
        for consume_entry in at_begin.get('consume', []):
            q = consume_entry['queue']
            if queues.get(q, False):
                resource_consumes.append(q)
            else:
                consumes_from.append(q)
                if q not in queue_consumers:
                    queue_consumers[q] = []
                queue_consumers[q].append(act_name)

        # Parse at_end produce (across all arcs)
        for arc in act_spec.get('at_end', []):
            for produce_entry in arc.get('produce', []):
                q = produce_entry['queue']
                token_source = produce_entry.get('token_source', '')

                if queues.get(q, False):
                    resource_produces.append(q)
                else:
                    produces_to.append(q)
                    if token_source == 'new':
                        creates_new = True

        activity = ACDActivity(
            name=act_name,
            priority=act_spec.get('priority', 0),
            consumes_from=consumes_from,
            produces_to=produces_to,
            resource_consumes=resource_consumes,
            resource_produces=resource_produces,
            creates_new_tokens=creates_new,
        )
        activities.append(activity)

    # Build adjacency: A -> B if A produces to queue Q and B consumes from Q
    # Only for non-resource queues (entity flow)
    adjacency: Dict[str, List[str]] = {a.name: [] for a in activities}

    for act in activities:
        for q in act.produces_to:
            # Find all activities that consume from this queue
            consumers = queue_consumers.get(q, [])
            for consumer in consumers:
                if consumer not in adjacency[act.name]:
                    adjacency[act.name].append(consumer)

    # Identify source activities: those that create new entity tokens
    # and consume only from resource queues (no upstream entity dependency)
    source_activities = []
    for act in activities:
        if act.creates_new_tokens and len(act.consumes_from) == 0:
            source_activities.append(act.name)

    # If no source found with strict criterion, use activities that create new tokens
    if not source_activities:
        for act in activities:
            if act.creates_new_tokens:
                source_activities.append(act.name)

    # Identify sink queues: non-resource queues that no activity consumes from
    all_consumed_queues = set()
    for act in activities:
        all_consumed_queues.update(act.consumes_from)

    sink_queues = set()
    for q_name, is_resource in queues.items():
        if not is_resource and q_name not in all_consumed_queues:
            sink_queues.add(q_name)

    # Identify sink activities: those that produce entity tokens to sink queues
    sink_activities = []
    for act in activities:
        produces_to_sink = any(q in sink_queues for q in act.produces_to)
        if produces_to_sink:
            sink_activities.append(act.name)

    # Also check: activities with no successors in the adjacency graph
    if not sink_activities:
        for act in activities:
            if not adjacency.get(act.name, []):
                sink_activities.append(act.name)

    return ACDGraph(
        name=spec.get('model_name', 'unnamed'),
        activities=activities,
        queues=queues,
        adjacency=adjacency,
        source_activities=source_activities,
        sink_activities=sink_activities,
        sink_queues=sink_queues,
    )


def enumerate_acd_paths(
    acd: ACDGraph,
    max_cycle_traversals: int = 1
) -> List[List[str]]:
    """
    Enumerate all entity paths from source to sink activities.

    Args:
        acd: Parsed ACD graph
        max_cycle_traversals: Maximum times a cycle can be traversed (default 1)

    Returns:
        List of paths, where each path is a list of activity names
    """
    paths = []
    back_edges = acd.find_back_edges()

    for source in acd.source_activities:
        for sink in acd.sink_activities:
            if source == sink:
                paths.append([source])
                continue

            _dfs_enumerate(
                current=source,
                sink=sink,
                adj=acd.adjacency,
                path=[source],
                visited={source},
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
    """DFS helper for path enumeration with cycle control."""
    if current == sink:
        paths.append(path.copy())
        return

    for neighbor in adj.get(current, []):
        edge = (current, neighbor)
        is_back_edge = edge in back_edges

        if is_back_edge:
            if cycle_counts[edge] >= max_cycle_traversals:
                continue
            cycle_counts[edge] += 1
            path.append(neighbor)
            _dfs_enumerate(
                current=neighbor, sink=sink, adj=adj, path=path,
                visited=visited, back_edges=back_edges,
                cycle_counts=cycle_counts,
                max_cycle_traversals=max_cycle_traversals,
                paths=paths
            )
            path.pop()
            cycle_counts[edge] -= 1

        elif neighbor not in visited:
            visited.add(neighbor)
            path.append(neighbor)
            _dfs_enumerate(
                current=neighbor, sink=sink, adj=adj, path=path,
                visited=visited, back_edges=back_edges,
                cycle_counts=cycle_counts,
                max_cycle_traversals=max_cycle_traversals,
                paths=paths
            )
            path.pop()
            visited.remove(neighbor)


def compute_acd_smc(
    acd: ACDGraph,
    activity_het: Dict[str, int],
    het_control: int
) -> int:
    """
    Compute path-based SMC for ACD: deduplicated activity costs + control overhead.

    Each activity contributes two rules: at_begin + at_end.
    The activity_het dict maps activity names to their combined HET
    (at_begin_action_{name} + at_end_action_{name}).

    Algorithm:
      1. Enumerate all source-to-sink paths (back-edges removed)
      2. Remove duplicate paths
      3. Collect unique activities across all paths
      4. Sum their costs
      5. Add control overhead

    Args:
        acd: Parsed ACD graph
        activity_het: Dict mapping activity name -> combined HET (at_begin + at_end)
        het_control: Total HET of control rules

    Returns:
        SMC value (int)
    """
    paths = enumerate_acd_paths(acd, max_cycle_traversals=0)
    if not paths:
        return het_control

    # Remove duplicate paths
    unique_paths = list({tuple(p) for p in paths})

    # Collect unique activities across all paths
    unique_activities = set()
    for p in unique_paths:
        unique_activities.update(p)

    # Sum deduplicated activity costs
    c_entity = 0
    for act_name in unique_activities:
        het = _lookup_activity_het(act_name, activity_het)
        c_entity += het

    return c_entity + het_control


def _lookup_activity_het(activity_name: str, activity_het: Dict[str, int]) -> int:
    """Look up activity HET by name, trying multiple formats."""
    # Direct lookup
    if activity_name in activity_het:
        return activity_het[activity_name]

    # Lowercase
    name_lower = activity_name.lower()
    if name_lower in activity_het:
        return activity_het[name_lower]

    # Try with at_begin/at_end prefix patterns
    # The generated SimASM names rules as at_begin_action_{name} and at_end_action_{name}
    begin_key = f"at_begin_action_{name_lower}"
    end_key = f"at_end_action_{name_lower}"

    het = 0
    for key in activity_het:
        key_lower = key.lower()
        if key_lower == begin_key or key_lower == end_key:
            het += activity_het[key]

    if het > 0:
        return het

    return 0
