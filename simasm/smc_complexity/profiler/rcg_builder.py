"""
Build a Rule Call Graph (RCG) from a parsed Program AST.

Detects three types of call edges:
1. Static calls: RuleCallStmt with LiteralTerm target
2. Dynamic dispatch: LibCallStmt with func_name="apply_rule"
3. Conditional calls: calls nested inside IfStmt (guard captured)

For EG models, dispatch targets are resolved by scanning for
event_rule(e) := "literal" patterns across all rule bodies.
"""

from typing import Dict, List, Optional, Set, Tuple

from simasm.parser.ast import Program, RuleDecl, MainRuleDecl
from simasm.core.terms import LiteralTerm, LocationTerm, VariableTerm
from simasm.core.rules import (
    Stmt, SeqStmt, IfStmt, LetStmt, WhileStmt, ForallStmt,
    ChooseStmt, ParStmt, RuleCallStmt, LibCallStmt, UpdateStmt,
)

from .models import RCGNode, RCGEdge, RuleCallGraph


def build_rcg(program: Program) -> RuleCallGraph:
    """Build a Rule Call Graph from the AST."""
    dispatch_targets = resolve_dispatch_targets(program)

    all_rule_names = set()
    for rule in program.rules:
        all_rule_names.add(rule.name)
    if program.main_rule:
        all_rule_names.add(program.main_rule.name)

    nodes: Dict[str, RCGNode] = {}
    for name in all_rule_names:
        nodes[name] = RCGNode(
            rule_name=name,
            het_cost=0,
            is_init=False,
            is_recurring=False,
            is_control=False,
        )

    edges: List[RCGEdge] = []

    if program.main_rule:
        main_name = program.main_rule.name
        call_sites = _find_call_sites(program.main_rule.body, [])
        for target, guard in call_sites:
            if target in all_rule_names:
                edges.append(RCGEdge(main_name, target, guard=guard))

    for rule in program.rules:
        call_sites = _find_call_sites(rule.body, [])
        for target, guard in call_sites:
            if target == "__dispatch__":
                for dt in sorted(dispatch_targets):
                    if dt in all_rule_names:
                        edges.append(RCGEdge(rule.name, dt, guard="dispatch", is_dispatch=True))
            elif target in all_rule_names:
                edges.append(RCGEdge(rule.name, target, guard=guard))

    adjacency: Dict[str, List[RCGEdge]] = {name: [] for name in all_rule_names}
    for edge in edges:
        adjacency[edge.from_rule].append(edge)

    return RuleCallGraph(nodes=nodes, edges=edges, adjacency=adjacency)


def resolve_dispatch_targets(program: Program) -> Set[str]:
    """
    Scan all rule bodies for event_rule(e) := "literal" patterns.
    Returns the set of target rule name strings.
    """
    targets: Set[str] = set()
    all_bodies = []
    for rule in program.rules:
        all_bodies.append(rule.body)
    if program.main_rule:
        all_bodies.append(program.main_rule.body)
    if program.init and program.init.body:
        all_bodies.append(program.init.body)

    for body in all_bodies:
        _collect_dispatch_targets(body, targets)

    return targets


def _collect_dispatch_targets(stmt: Stmt, targets: Set[str]):
    if isinstance(stmt, UpdateStmt):
        if (isinstance(stmt.location, LocationTerm)
                and stmt.location.func_name == "event_rule"
                and isinstance(stmt.value, LiteralTerm)
                and isinstance(stmt.value.value, str)):
            targets.add(stmt.value.value)
    elif isinstance(stmt, SeqStmt):
        for s in stmt.statements:
            _collect_dispatch_targets(s, targets)
    elif isinstance(stmt, IfStmt):
        _collect_dispatch_targets(stmt.then_body, targets)
        for _, body in stmt.elseif_branches:
            _collect_dispatch_targets(body, targets)
        if stmt.else_body:
            _collect_dispatch_targets(stmt.else_body, targets)
    elif isinstance(stmt, LetStmt):
        pass
    elif isinstance(stmt, (WhileStmt, ForallStmt, ChooseStmt)):
        _collect_dispatch_targets(stmt.body, targets)
    elif isinstance(stmt, ParStmt):
        _collect_dispatch_targets(stmt.body, targets)


def _find_call_sites(
    stmt: Stmt,
    guards: List[str],
) -> List[Tuple[str, Optional[str]]]:
    """
    Recursively walk stmt, yielding (target_rule_name, guard_string) pairs.
    """
    results: List[Tuple[str, Optional[str]]] = []
    guard_str = " && ".join(guards) if guards else None

    if isinstance(stmt, RuleCallStmt):
        if isinstance(stmt.rule_name, LiteralTerm) and isinstance(stmt.rule_name.value, str):
            results.append((stmt.rule_name.value, guard_str))
        elif isinstance(stmt.rule_name, VariableTerm):
            results.append((stmt.rule_name.name, guard_str))

    elif isinstance(stmt, LibCallStmt) and stmt.func_name == "apply_rule":
        results.append(("__dispatch__", guard_str))

    elif isinstance(stmt, SeqStmt):
        for s in stmt.statements:
            results.extend(_find_call_sites(s, guards))

    elif isinstance(stmt, IfStmt):
        cond_str = _condition_summary(stmt.condition)
        results.extend(_find_call_sites(stmt.then_body, guards + [cond_str]))
        for cond, body in stmt.elseif_branches:
            results.extend(_find_call_sites(body, guards + [_condition_summary(cond)]))
        if stmt.else_body:
            results.extend(_find_call_sites(stmt.else_body, guards + ["else"]))

    elif isinstance(stmt, (WhileStmt,)):
        results.extend(_find_call_sites(stmt.body, guards + [_condition_summary(stmt.condition)]))

    elif isinstance(stmt, (ForallStmt, ChooseStmt)):
        results.extend(_find_call_sites(stmt.body, guards))

    elif isinstance(stmt, ParStmt):
        results.extend(_find_call_sites(stmt.body, guards))

    return results


def _condition_summary(term) -> str:
    """Short human-readable summary of a condition term."""
    s = str(term)
    if len(s) > 60:
        return s[:57] + "..."
    return s
