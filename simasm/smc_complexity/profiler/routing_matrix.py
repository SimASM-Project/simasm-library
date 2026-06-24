"""
Build routing probability matrix P and source vector s from a SchedulingSubgraph.

Handles:
- Self-loop edges → source rate (not routing)
- Single outgoing edge → P = 1.0
- Probabilistic branching (var < param / var >= param) → P from parameters
- State-dependent guards → P = 1.0 (not routing)
"""

import re
import warnings
from typing import Dict, List, Tuple

import numpy as np

from ..models import SchedulingSubgraph, SchedulingEdge


def build_routing_matrix(
    graph: SchedulingSubgraph,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Build routing probability matrix P and source vector s.

    Returns:
        P: |V|×|V| routing probability matrix
        s: |V| source rate vector
        vertex_names: ordered vertex list (index mapping)
    """
    vertex_names = list(graph.vertices)
    n = len(vertex_names)
    idx = {v: i for i, v in enumerate(vertex_names)}

    P = np.zeros((n, n))
    s = np.zeros(n)

    for vertex in vertex_names:
        edges = graph.adjacency.get(vertex, [])
        self_loops = [e for e in edges if e.from_vertex == e.to_vertex]
        routing_edges = [e for e in edges if e.from_vertex != e.to_vertex]

        # Self-loops with positive delay define source rate
        for e in self_loops:
            if e.mean_delay > 0:
                s[idx[vertex]] = 1.0 / e.mean_delay

        # Routing edges define P
        if not routing_edges:
            continue

        _assign_routing_probabilities(P, idx, vertex, routing_edges, graph.parameters)

    # Detect implicit feedback loops from probabilistic conditions in rules
    _apply_feedback_probabilities(P, idx, graph)

    return P, s, vertex_names


def _apply_feedback_probabilities(
    P: np.ndarray,
    idx: Dict[str, int],
    graph: SchedulingSubgraph,
) -> None:
    """
    Detect implicit feedback routing from probabilistic conditions.

    Two patterns:
    1. Edge condition contains probabilistic marker (e.g., fb_rand < feedback_prob
       combined with queue guard) — the edge carries flow at rate = probability.
    2. Implicit feedback: feedback_prob parameter exists, and the last Finish vertex
       has a queue-pull edge back into the service pipeline. The probabilistic
       routing is encoded as a state change (queue increment) in the rule body,
       not as a condition on the scheduling edge.
    """
    feedback_prob = graph.parameters.get("feedback_prob")

    for e in graph.edges:
        if e.from_vertex == e.to_vertex:
            continue
        if not _is_queue_pull_edge(e):
            continue

        from_idx = idx[e.from_vertex]
        to_idx = idx[e.to_vertex]
        if P[from_idx, to_idx] != 0:
            continue

        # Pattern 1: condition itself contains probabilistic marker
        prob = _extract_probability_from_condition(e.condition, graph.parameters)
        if prob is not None and prob > 0:
            P[from_idx, to_idx] = prob
            continue

        # Pattern 2: implicit feedback via queue state manipulation
        # Only applies when:
        # - feedback_prob parameter exists
        # - This edge is from the last Finish vertex going back to Start
        # - The Finish vertex has NO other routing edge already assigned
        #   (if it does, the feedback is handled explicitly via a routing vertex)
        if feedback_prob is not None and feedback_prob > 0:
            # Check if this Finish vertex already has routing flow assigned
            if P[from_idx].sum() == 0 and _is_feedback_return_edge(e, graph):
                P[from_idx, to_idx] = feedback_prob


def _is_feedback_return_edge(edge: SchedulingEdge, graph: SchedulingSubgraph) -> bool:
    """
    Check if a queue-pull edge represents a feedback return path.

    True if: it's from a Finish_N vertex going back to Start_M where M < N
    (going backward in the pipeline). For single-station models (only one
    station), Finish_1 → Start_1 is the feedback path.
    """
    from_lower = edge.from_vertex.lower()
    to_lower = edge.to_vertex.lower()

    if "finish" not in from_lower or "start" not in to_lower:
        return False

    from_num = _extract_station_number(from_lower)
    to_num = _extract_station_number(to_lower)

    if not from_num or not to_num:
        return False

    # Going backward (e.g., Finish_5 → Start_1): always feedback
    if int(to_num) < int(from_num):
        return True

    # Same station (e.g., Finish_1 → Start_1): only if single-station model
    if from_num == to_num:
        finish_nums = []
        for v in graph.vertices:
            if "finish" in v.lower():
                n = _extract_station_number(v.lower())
                if n:
                    finish_nums.append(int(n))
        # Single station model: max Finish = 1, only 1 station
        if len(finish_nums) == 1:
            return True

    return False


def _extract_probability_from_condition(
    condition: str,
    parameters: Dict[str, float],
) -> "float | None":
    """
    Extract a routing probability from an edge condition string.

    Handles:
    - Threshold pattern: 'fb_rand < feedback_prob' → parameters[feedback_prob]
    - Complement pattern: 'fb_rand >= feedback_prob' → 1 - parameters[feedback_prob]
    - Symbolic: 'Var(feedback)' or 'feedback' → parameters[feedback_prob] if exists
    - Symbolic complement: 'Var(not_feedback)' → 1 - parameters[feedback_prob]
    """
    cond_lower = condition.lower()

    # Symbolic conditions: Var(feedback) or Var(not_feedback)
    if "not_feedback" in cond_lower or "not feedback" in cond_lower:
        if "feedback_prob" in parameters:
            return 1.0 - parameters["feedback_prob"]
    if re.search(r"\bfeedback\b", cond_lower) and "not" not in cond_lower:
        if "feedback_prob" in parameters:
            return parameters["feedback_prob"]

    # Must contain a probabilistic indicator for threshold patterns
    if not ("rand" in cond_lower or "decision" in cond_lower):
        return None

    # Look for < threshold comparison
    lt_match = _LT_PATTERN.search(condition)
    if lt_match:
        param_name = lt_match.group(2)
        if param_name in parameters:
            return parameters[param_name]

    # Look for >= threshold comparison (complement)
    ge_match = _GE_PATTERN.search(condition)
    if ge_match:
        param_name = ge_match.group(2)
        if param_name in parameters:
            return 1.0 - parameters[param_name]

    return None


def _assign_routing_probabilities(
    P: np.ndarray,
    idx: Dict[str, int],
    from_vertex: str,
    edges: List[SchedulingEdge],
    parameters: Dict[str, float],
) -> None:
    """Assign routing probabilities for outgoing edges of a vertex."""
    # Separate edges into routing vs queue-pull
    # Queue-pull edges (condition checks queue_count > 0) trigger service for
    # the NEXT waiting entity — they don't route the current entity's flow.
    routing_edges = []
    for e in edges:
        if _is_queue_pull_edge(e):
            continue
        routing_edges.append(e)

    if not routing_edges:
        # All outgoing edges are queue-pull → this is a terminal vertex
        # for flow purposes (entities exit/depart here). P row stays zero.
        return

    if len(routing_edges) == 1:
        e = routing_edges[0]
        # Check if this single edge has a probabilistic condition
        prob = _extract_probability_from_condition(e.condition, parameters)
        if prob is not None:
            P[idx[from_vertex], idx[e.to_vertex]] += prob
        else:
            P[idx[from_vertex], idx[e.to_vertex]] += 1.0
        return

    # Check for broadcast pattern (Fork: all edges go to different targets
    # with independent state guards — each gets P=1.0)
    if _is_broadcast_pattern(routing_edges):
        for e in routing_edges:
            P[idx[from_vertex], idx[e.to_vertex]] += 1.0
        return

    # Multiple routing edges — check for probabilistic branching
    probs = _parse_edge_probabilities(routing_edges, parameters)
    if probs is not None:
        for e, p in zip(routing_edges, probs):
            P[idx[from_vertex], idx[e.to_vertex]] += p
    else:
        n_edges = len(routing_edges)
        for e in routing_edges:
            P[idx[from_vertex], idx[e.to_vertex]] += 1.0 / n_edges
        conditions = [e.condition for e in routing_edges]
        warnings.warn(
            f"routing_matrix: cannot parse conditions {conditions} "
            f"for edges from '{from_vertex}', using equal split",
            stacklevel=3,
        )


def _is_broadcast_pattern(edges: List[SchedulingEdge]) -> bool:
    """
    Detect fork/broadcast pattern: multiple edges to distinct targets,
    each with an independent state guard referencing a different queue variable.

    In fork-join models, the Fork event sends work to ALL branches simultaneously.
    Each edge has a condition like `queue_count_N > 0 and server_count_N < capacity`
    where N differs for each edge. This is broadcast (P=1 for each), not routing.
    """
    if len(edges) < 2:
        return False

    targets = set()
    all_state_guarded = True
    for e in edges:
        if e.to_vertex in targets:
            return False  # Duplicate targets → not broadcast
        targets.add(e.to_vertex)
        if not _is_state_guard(e.condition):
            all_state_guarded = False

    if not all_state_guarded:
        return False

    # All edges go to distinct targets with state guards.
    # Check that conditions reference different queue variables (not all the same).
    queue_refs = set()
    for e in edges:
        # Extract queue variable name from condition
        match = re.search(r"queue_count_(\d+)|branch_queue_(\d+)", e.condition.lower())
        if match:
            queue_refs.add(match.group(0))
    # If each edge references a different queue, it's broadcast
    return len(queue_refs) >= len(edges)


def _parse_edge_probabilities(
    edges: List[SchedulingEdge],
    parameters: Dict[str, float],
) -> "List[float] | None":
    """
    Try to extract routing probabilities from edge conditions.

    Handles:
    - All "true" or state-guard (not queue-pull) → all P = 1.0
    - Complementary pair: var < param / var >= param → (param, 1-param)
    """
    conditions = [e.condition for e in edges]

    # Case: all conditions are "true" or server-availability guards
    # (these edges all fire for the current entity, so each gets P=1.0
    #  but we normalize below since row sum should be ≤ 1)
    all_non_probabilistic = all(
        c == "true" or c == "" or _is_state_guard(c) for c in conditions
    )
    if all_non_probabilistic:
        # All edges are unconditional or state-gated (server availability).
        # In steady-state, exactly one fires per event. Split equally.
        return [1.0 / len(edges)] * len(edges)

    # Case: complementary probabilistic pair
    if len(edges) == 2:
        prob = _parse_complementary_pair(conditions[0], conditions[1], parameters)
        if prob is not None:
            return [prob, 1.0 - prob]
        # Try reversed
        prob = _parse_complementary_pair(conditions[1], conditions[0], parameters)
        if prob is not None:
            return [1.0 - prob, prob]

    return None


def _is_state_guard(condition: str) -> bool:
    """Check if a condition is a state-dependent guard (not probabilistic routing)."""
    if condition == "true":
        return False
    if condition == "else":
        return False
    cond_lower = condition.lower()
    # Probabilistic conditions reference random variables or thresholds with < / >=
    # e.g., "fb_rand < feedback_prob" — these are NOT state guards
    if "rand" in cond_lower or "prob" in cond_lower or "decision" in cond_lower:
        return False
    # State guards reference queue/server state variables
    if "count" in cond_lower or "capacity" in cond_lower or "length" in cond_lower:
        return True
    if "queue" in cond_lower or "server" in cond_lower:
        return True
    return False


def _is_queue_pull_edge(edge: SchedulingEdge) -> bool:
    """
    Check if an edge is a 'pull next entity from queue' trigger.

    These edges fire when a server finishes and checks if more work is waiting.
    They trigger service for a DIFFERENT entity, not routing the current one.

    Pattern: Finish_N → Start_N (or Start_N → Start_N self-loop) with a
    queue_count > 0 condition. Only applies to Finish→Start edges within
    the same station or self-loops.
    """
    cond_lower = edge.condition.lower()
    # Must reference queue state
    has_queue_check = ("queue_count" in cond_lower or "queue" in cond_lower) and ">" in edge.condition
    if not has_queue_check:
        return False

    from_lower = edge.from_vertex.lower()
    to_lower = edge.to_vertex.lower()

    # Self-loop (Start_N → Start_N): definitely queue-pull
    if from_lower == to_lower:
        return True

    # Finish_N → Start_N (same station number): queue-pull
    if "finish" in from_lower and "start" in to_lower:
        # Extract station numbers to verify same station
        from_num = _extract_station_number(from_lower)
        to_num = _extract_station_number(to_lower)
        if from_num == to_num:
            return True

    return False


def _extract_station_number(vertex_name: str) -> str:
    """Extract station number suffix (e.g., 'finish_1' → '1', 'finish' → '')."""
    parts = vertex_name.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[1]
    return ""


# Pattern: var < param or var < literal
# Handles both raw format (fb_rand < feedback_prob) and
# AST repr format (Var(fb_rand) < Var(feedback_prob))
_LT_PATTERN = re.compile(r"(?:Var\()?(\w+)\)?\s*<\s*(?:Var\()?(\w+)\)?")
_GE_PATTERN = re.compile(r"(?:Var\()?(\w+)\)?\s*>=\s*(?:Var\()?(\w+)\)?")


def _parse_complementary_pair(
    cond_lt: str,
    cond_ge: str,
    parameters: Dict[str, float],
) -> "float | None":
    """
    Parse a complementary pair (var < param, var >= param) → probability.

    Returns the probability for the < branch, or None if cannot parse.
    """
    lt_match = _LT_PATTERN.search(cond_lt)
    ge_match = _GE_PATTERN.search(cond_ge)

    if lt_match is None or ge_match is None:
        return None

    lt_var, lt_param = lt_match.group(1), lt_match.group(2)
    ge_var, ge_param = ge_match.group(1), ge_match.group(2)

    # Must reference the same variable and parameter
    if lt_var != ge_var or lt_param != ge_param:
        return None

    # Resolve parameter value
    param_name = lt_param
    if param_name in parameters:
        return parameters[param_name]

    # Try as literal float
    try:
        return float(param_name)
    except ValueError:
        return None
