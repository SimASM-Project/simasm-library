"""
Classify rules as init, recurring, or control based on RCG reachability.

EG main rule structure (two consecutive IfStmts):
    if sim_clocktime == 0.0 and ... then   // init guard
        initialisation_routine()
    endif
    if ... and sim_clocktime < sim_end_time then   // sim guard
        timing_routine()
        event_routine()
    endif
"""

from typing import Dict, Set

from simasm.parser.ast import Program
from simasm.core.rules import SeqStmt, IfStmt, RuleCallStmt
from simasm.core.terms import LiteralTerm

from .models import RuleCallGraph

# "select_imminent" and "update_event_list" reserved for future DEVS-style models
CONTROL_RULE_NAMES = {
    "main", "timing_routine", "event_routine",
    "select_imminent", "update_event_list",
}


def classify_rules(
    program: Program,
    rcg: RuleCallGraph,
) -> Dict[str, str]:
    """
    Classify each rule as 'init', 'recurring', or 'control'.

    Strategy:
    1. Parse main rule body to find init-branch vs sim-branch calls
    2. Init-branch targets (and their transitive callees) → 'init'
    3. Sim-branch targets (and their transitive callees) → 'recurring'
    4. Main rule itself → 'control'
    5. Named control rules → 'control' (override)
    """
    init_direct, sim_direct = _parse_main_branches(program)

    init_reachable = _transitive_callees(init_direct, rcg)
    sim_reachable = _transitive_callees(sim_direct, rcg)

    classification: Dict[str, str] = {}
    for name in rcg.nodes:
        if name.lower() in CONTROL_RULE_NAMES:
            classification[name] = "control"
        elif name in sim_reachable:
            classification[name] = "recurring"
        elif name in init_reachable:
            classification[name] = "init"
        else:
            classification[name] = "recurring"

    if program.main_rule:
        classification[program.main_rule.name] = "control"

    return classification


def _parse_main_branches(program: Program):
    """
    Walk main rule body to find init-branch and sim-branch rule calls.
    Handles the two-IfStmt pattern used by all EG models.
    """
    init_calls: Set[str] = set()
    sim_calls: Set[str] = set()

    if program.main_rule is None:
        return init_calls, sim_calls

    body = program.main_rule.body
    if_stmts = []

    if isinstance(body, SeqStmt):
        for s in body.statements:
            if isinstance(s, IfStmt):
                if_stmts.append(s)
    elif isinstance(body, IfStmt):
        if_stmts.append(body)

    if len(if_stmts) >= 2:
        _collect_direct_calls(if_stmts[0].then_body, init_calls)
        _collect_direct_calls(if_stmts[1].then_body, sim_calls)
    elif len(if_stmts) == 1:
        stmt = if_stmts[0]
        if stmt.else_body:
            _collect_direct_calls(stmt.then_body, init_calls)
            _collect_direct_calls(stmt.else_body, sim_calls)
        else:
            _collect_direct_calls(stmt.then_body, sim_calls)

    return init_calls, sim_calls


def _collect_direct_calls(stmt, calls: Set[str]):
    if isinstance(stmt, RuleCallStmt):
        if isinstance(stmt.rule_name, LiteralTerm) and isinstance(stmt.rule_name.value, str):
            calls.add(stmt.rule_name.value)
    elif isinstance(stmt, SeqStmt):
        for s in stmt.statements:
            _collect_direct_calls(s, calls)
    elif isinstance(stmt, IfStmt):
        _collect_direct_calls(stmt.then_body, calls)
        if stmt.else_body:
            _collect_direct_calls(stmt.else_body, calls)


def _transitive_callees(seeds: Set[str], rcg: RuleCallGraph) -> Set[str]:
    reachable: Set[str] = set()
    worklist = list(seeds)
    while worklist:
        name = worklist.pop()
        if name in reachable:
            continue
        reachable.add(name)
        for edge in rcg.adjacency.get(name, []):
            if edge.to_rule not in reachable:
                worklist.append(edge.to_rule)
    return reachable
