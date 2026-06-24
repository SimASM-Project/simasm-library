"""
Build a SchedulingSubgraph from the ASM program text alone.

Produces the same SchedulingSubgraph dataclass that eg_graph.parse_eg_json()
returns, enabling reuse of cycle_finder.find_fundamental_cycles().
"""

import re
import warnings
from typing import Dict, List, Optional, Set, Tuple

from simasm.parser.ast import Program
from simasm.core.terms import (
    Term, LiteralTerm, VariableTerm, LocationTerm, BinaryOpTerm, NewTerm,
)
from simasm.core.rules import (
    Stmt, SeqStmt, IfStmt, LetStmt, UpdateStmt, LibCallStmt,
    WhileStmt, ForallStmt, ChooseStmt, ParStmt,
)

from ..models import SchedulingSubgraph, SchedulingEdge
from .models import StreamInfo, RuleCallGraph


def build_scheduling_subgraph(
    program: Program,
    streams: Dict[str, StreamInfo],
    rule_classification: Dict[str, str],
    rcg: RuleCallGraph,
) -> SchedulingSubgraph:
    """
    Build a SchedulingSubgraph from the ASM, equivalent to parse_eg_json().
    """
    dispatch_targets = _get_event_rule_names(rcg)
    rule_bodies = {r.name: r.body for r in program.rules}

    stream_names = set(streams.keys())
    all_edges: List[SchedulingEdge] = []
    vertex_set: Set[str] = set()

    for rule_name in dispatch_targets:
        body = rule_bodies.get(rule_name)
        if body is None:
            continue
        from_vertex = _rule_name_to_vertex(rule_name)
        vertex_set.add(from_vertex)
        edges = _extract_scheduling_edges(from_vertex, body, stream_names, streams)
        for e in edges:
            vertex_set.add(e.to_vertex)
        all_edges.extend(edges)

    source_vertex = _detect_source_vertex(program, stream_names, streams)
    if source_vertex is None and vertex_set:
        source_vertex = sorted(vertex_set)[0]
    if source_vertex is None and vertex_set:
        raise ValueError("Cannot determine source vertex for non-empty scheduling subgraph")

    init_params = _collect_init_params(program)
    t_sim = init_params.get("sim_end_time", 10000.0)

    vertices = sorted(vertex_set)

    adjacency: Dict[str, List[SchedulingEdge]] = {v: [] for v in vertices}
    for e in all_edges:
        if e.from_vertex in adjacency:
            adjacency[e.from_vertex].append(e)

    random_streams: Dict[str, dict] = {}
    for name, info in streams.items():
        random_streams[name] = {
            "distribution": info.distribution,
            "params": dict(zip(
                [f"param_{i}" for i in range(len(info.param_exprs))],
                [str(v) for v in info.param_exprs],
            )),
        }

    parameters: Dict[str, float] = {}
    for name, val in init_params.items():
        parameters[name] = val

    return SchedulingSubgraph(
        vertices=vertices,
        edges=all_edges,
        adjacency=adjacency,
        source_vertex=source_vertex,
        random_streams=random_streams,
        parameters=parameters,
        t_sim=t_sim,
    )


def _get_event_rule_names(rcg: RuleCallGraph) -> Set[str]:
    """Get rule names that are dispatch targets (event rules)."""
    targets: Set[str] = set()
    for edge in rcg.edges:
        if edge.is_dispatch:
            targets.add(edge.to_rule)
    return targets


def _rule_name_to_vertex(rule_name: str) -> str:
    """
    Convert ASM rule name to JSON-style vertex name.
    event_arrive -> Arrive
    event_start_1 -> Start_1
    event_attempt__to__depart -> Attempt_To_Depart
    """
    name = rule_name
    if name.startswith("event_"):
        name = name[6:]

    segments = name.split("__")
    result_parts = []
    for segment in segments:
        sub_parts = segment.split("_")
        for sp in sub_parts:
            if sp and not sp[0].isdigit():
                sp = sp[0].upper() + sp[1:]
            result_parts.append(sp)

    return "_".join(result_parts)


def _extract_scheduling_edges(
    from_vertex: str,
    body: Stmt,
    stream_names: Set[str],
    streams: Dict[str, StreamInfo],
) -> List[SchedulingEdge]:
    """Extract scheduling edges from a single event rule body."""
    groups = _find_scheduling_groups(body, stream_names, streams)
    edges = []
    for target_rule, delay_expr, mean_delay, condition in groups:
        to_vertex = _rule_name_to_vertex(target_rule)
        edges.append(SchedulingEdge(
            from_vertex=from_vertex,
            to_vertex=to_vertex,
            delay_expr=delay_expr,
            condition=condition,
            mean_delay=mean_delay,
        ))
    return edges


def _find_scheduling_groups(
    stmt: Stmt,
    stream_names: Set[str],
    streams: Dict[str, StreamInfo],
    condition: str = "true",
) -> List[Tuple[str, str, float, str]]:
    """
    Find scheduling statement groups in a rule body.

    Assumes ``let e = new Event``, ``event_rule(e) := ...``, and
    ``event_scheduled_time(e) := ...`` are siblings within the same SeqStmt
    block. Handles both orderings (rule-before-time and time-before-rule).

    Returns list of (target_rule_name, delay_expr_str, mean_delay, condition).
    """
    results: List[Tuple[str, str, float, str]] = []

    if isinstance(stmt, SeqStmt):
        pending_lets: Dict[str, str] = {}
        pending_targets: Dict[str, str] = {}
        pending_times: Dict[str, Tuple[str, float]] = {}

        for s in stmt.statements:
            if isinstance(s, LetStmt) and isinstance(s.value, NewTerm):
                pending_lets[s.var_name] = s.value.domain

            elif isinstance(s, UpdateStmt):
                _process_update(s, pending_lets, pending_targets, pending_times,
                                stream_names, streams, condition, results)

            elif isinstance(s, IfStmt):
                cond_str = _short_condition(s.condition)
                results.extend(_find_scheduling_groups(
                    s.then_body, stream_names, streams, cond_str))
                for cond, branch_body in s.elseif_branches:
                    results.extend(_find_scheduling_groups(
                        branch_body, stream_names, streams, _short_condition(cond)))
                if s.else_body:
                    results.extend(_find_scheduling_groups(
                        s.else_body, stream_names, streams, "else"))

            elif isinstance(s, (WhileStmt, ForallStmt, ChooseStmt)):
                results.extend(_find_scheduling_groups(
                    s.body, stream_names, streams, condition))
            elif isinstance(s, ParStmt):
                results.extend(_find_scheduling_groups(
                    s.body, stream_names, streams, condition))

        if pending_times:
            orphaned = set(pending_times.keys()) - set(pending_targets.keys())
            for var in orphaned:
                warnings.warn(
                    f"Orphaned event_scheduled_time assignment for '{var}' "
                    f"with no matching event_rule target",
                    stacklevel=2,
                )

    elif isinstance(stmt, IfStmt):
        cond_str = _short_condition(stmt.condition)
        results.extend(_find_scheduling_groups(
            stmt.then_body, stream_names, streams, cond_str))
        for cond, branch_body in stmt.elseif_branches:
            results.extend(_find_scheduling_groups(
                branch_body, stream_names, streams, _short_condition(cond)))
        if stmt.else_body:
            results.extend(_find_scheduling_groups(
                stmt.else_body, stream_names, streams, "else"))

    return results


def _process_update(
    stmt: UpdateStmt,
    pending_lets: Dict[str, str],
    pending_targets: Dict[str, str],
    pending_times: Dict[str, Tuple[str, float]],
    stream_names: Set[str],
    streams: Dict[str, StreamInfo],
    condition: str,
    results: List[Tuple[str, str, float, str]],
):
    loc = stmt.location
    if not isinstance(loc, LocationTerm) or len(loc.arguments) != 1:
        return

    arg = loc.arguments[0]
    if not isinstance(arg, VariableTerm):
        return
    entity_var = arg.name

    if loc.func_name == "event_rule":
        if isinstance(stmt.value, LiteralTerm) and isinstance(stmt.value.value, str):
            pending_targets[entity_var] = stmt.value.value
            if entity_var in pending_times:
                delay_expr, mean_delay = pending_times.pop(entity_var)
                results.append((stmt.value.value, delay_expr, mean_delay, condition))

    elif loc.func_name == "event_scheduled_time":
        delay_expr, mean_delay = _resolve_delay_term(stmt.value, stream_names, streams)
        if entity_var in pending_targets:
            target = pending_targets[entity_var]
            results.append((target, delay_expr, mean_delay, condition))
        else:
            pending_times[entity_var] = (delay_expr, mean_delay)


def _resolve_delay_term(
    term: Term,
    stream_names: Set[str],
    streams: Dict[str, StreamInfo],
) -> Tuple[str, float]:
    """
    Resolve a delay expression to (delay_expr_string, mean_delay).

    Handles:
    - sim_clocktime + stream_var -> (stream_var, stream.mean_delay)
    - sim_clocktime + literal    -> (str(literal), float(literal))
    - sim_clocktime (bare)       -> ("0", 0.0)
    """
    if isinstance(term, VariableTerm) and term.name == "sim_clocktime":
        return ("0", 0.0)

    if isinstance(term, LocationTerm) and term.func_name == "sim_clocktime" and not term.arguments:
        return ("0", 0.0)

    if isinstance(term, BinaryOpTerm) and term.operator == "+":
        left_is_clock = _is_sim_clocktime(term.left)
        right_is_clock = _is_sim_clocktime(term.right)

        if left_is_clock:
            return _resolve_delay_operand(term.right, stream_names, streams)
        if right_is_clock:
            return _resolve_delay_operand(term.left, stream_names, streams)

    return (str(term), 0.0)


def _is_sim_clocktime(term: Term) -> bool:
    if isinstance(term, VariableTerm) and term.name == "sim_clocktime":
        return True
    if isinstance(term, LocationTerm) and term.func_name == "sim_clocktime" and not term.arguments:
        return True
    return False


def _resolve_delay_operand(
    term: Term,
    stream_names: Set[str],
    streams: Dict[str, StreamInfo],
) -> Tuple[str, float]:
    """Resolve the non-clocktime operand of a delay expression."""
    if isinstance(term, VariableTerm) and term.name in stream_names:
        return (term.name, streams[term.name].mean_delay)
    if isinstance(term, LocationTerm) and term.func_name in stream_names:
        return (term.func_name, streams[term.func_name].mean_delay)
    if isinstance(term, LiteralTerm):
        try:
            return (str(term.value), float(term.value))
        except (ValueError, TypeError):
            pass
    if isinstance(term, VariableTerm):
        return (term.name, 0.0)
    return (str(term), 0.0)


def _detect_source_vertex(
    program: Program,
    stream_names: Set[str],
    streams: Dict[str, StreamInfo],
) -> Optional[str]:
    """Detect source vertex from init block's first scheduling statement."""
    init_rule = None
    for rule in program.rules:
        if rule.name in ("initialisation_routine", "initialization_routine", "init_routine"):
            init_rule = rule
            break

    if init_rule is None:
        return None

    groups = _find_scheduling_groups(init_rule.body, stream_names, streams)
    if groups:
        return _rule_name_to_vertex(groups[0][0])
    return None


def _collect_init_params(program: Program) -> Dict[str, float]:
    """Collect init params (reuse logic from stream_extractor)."""
    from .stream_extractor import resolve_init_params
    return resolve_init_params(program)


def _short_condition(term: Term) -> str:
    s = str(term)
    if len(s) > 80:
        return s[:77] + "..."
    return s
