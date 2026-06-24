"""
Tag RCG nodes with stream variables, classification, and HET costs.

Moved from __init__.py to keep the API module thin.
"""

from typing import Dict, List

from simasm.core.terms import VariableTerm, LocationTerm, BinaryOpTerm, UnaryOpTerm
from simasm.core.rules import (
    SeqStmt, IfStmt, LetStmt, UpdateStmt,
    WhileStmt, ForallStmt, ChooseStmt, ParStmt,
)

from simasm.parser.ast import Program
from .models import RuleCallGraph, StreamInfo


def tag_rcg_streams(
    program: Program,
    rcg: RuleCallGraph,
    streams: Dict[str, StreamInfo],
) -> None:
    """Tag each RCG node with the stream variable names used in its rule body."""
    stream_var_to_name = {
        s.var_name: (s.stream_name or s.var_name) for s in streams.values()
    }
    for rule in program.rules:
        node = rcg.nodes.get(rule.name)
        _tag_rule_streams(rule.body, stream_var_to_name, node)


def _tag_rule_streams(stmt, stream_var_to_name: Dict[str, str], node) -> None:
    if node is None:
        return
    if isinstance(stmt, SeqStmt):
        for s in stmt.statements:
            _tag_rule_streams(s, stream_var_to_name, node)
    elif isinstance(stmt, UpdateStmt):
        _check_term_for_streams(stmt.value, stream_var_to_name, node)
    elif isinstance(stmt, LetStmt):
        _check_term_for_streams(stmt.value, stream_var_to_name, node)
    elif isinstance(stmt, IfStmt):
        _tag_rule_streams(stmt.then_body, stream_var_to_name, node)
        for _, body in stmt.elseif_branches:
            _tag_rule_streams(body, stream_var_to_name, node)
        if stmt.else_body:
            _tag_rule_streams(stmt.else_body, stream_var_to_name, node)
    elif isinstance(stmt, (WhileStmt, ForallStmt, ChooseStmt, ParStmt)):
        _tag_rule_streams(stmt.body, stream_var_to_name, node)


def _check_term_for_streams(term, stream_var_to_name: Dict[str, str], node) -> None:
    if isinstance(term, VariableTerm) and term.name in stream_var_to_name:
        sname = stream_var_to_name[term.name]
        if sname not in node.streams:
            node.streams.append(sname)
    elif isinstance(term, LocationTerm):
        if term.func_name in stream_var_to_name:
            sname = stream_var_to_name[term.func_name]
            if sname not in node.streams:
                node.streams.append(sname)
        for arg in term.arguments:
            _check_term_for_streams(arg, stream_var_to_name, node)
    elif isinstance(term, BinaryOpTerm):
        _check_term_for_streams(term.left, stream_var_to_name, node)
        _check_term_for_streams(term.right, stream_var_to_name, node)
    elif isinstance(term, UnaryOpTerm):
        _check_term_for_streams(term.operand, stream_var_to_name, node)
