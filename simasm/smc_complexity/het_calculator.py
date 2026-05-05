"""
HET (Honest Evaluation Time) calculator using paper convention (Section 3.1).

Uses the main Lark parser to parse .simasm files, then walks the AST
to compute HET per rule.

Paper convention for update rules:
    C_rule(f(t_bar) := t) = 1 + C_term(f(t_bar)) + C_term(t)

where C_term(f(t_bar)) = 1 + sum(C_term(t_i)), counting the function symbol.
Includes overhead costs: seq (+1), if (+1), new (=3), lib dispatch (+2).
"""

from pathlib import Path
from typing import Dict, Union

from simasm.parser.parser import parse_file, parse_string
from simasm.parser.ast import Program, RuleDecl, MainRuleDecl, InitBlock
from simasm.core.terms import (
    Term, LiteralTerm, VariableTerm, LocationTerm,
    BinaryOpTerm, UnaryOpTerm, ListTerm, TupleTerm,
    NewTerm, LibCallTerm, RndCallTerm,
)
from simasm.core.rules import (
    Stmt, SkipStmt, UpdateStmt, SeqStmt, IfStmt,
    WhileStmt, ForallStmt, LetStmt, RuleCallStmt, PrintStmt,
    ChooseStmt, ParStmt,
    LibCallStmt as LibCallStatement, RndCallStmt as RndCallStatement,
)

CONTROL_RULE_NAMES = {
    "initialisation_routine", "initialization_routine", "init_routine",
    "timing_routine", "event_routine", "main",
}

# Control overhead constants
C_STEP = 65       # Next-event algorithm step cost
C_INIT = 30       # Initialization cost
C_PM = 27         # Phase manager cost
C_PINIT = 24      # Phase init cost
C_PT = 26         # Phase timing cost
C_PD = 12         # Phase dispatch cost

# Control overhead for SMC v10: C_ctrl = C_STEP + C_PINIT = 89
C_CTRL = C_STEP + C_PINIT


def compute_event_het(
    simasm_path: Union[str, Path],
) -> Dict[str, int]:
    """
    Parse a .simasm file and compute HET for each event rule.

    Returns dict mapping rule name -> HET cost.
    Only event rules are included (control rules excluded).
    """
    program = parse_file(str(simasm_path))
    return compute_het_from_program(program)


def compute_event_het_from_string(source: str) -> Dict[str, int]:
    """Compute HET from a SimASM source string."""
    program = parse_string(source)
    return compute_het_from_program(program)


def compute_het_from_program(program: Program) -> Dict[str, int]:
    """Extract event rule HET costs from a parsed Program."""
    event_het = {}
    for rule in program.rules:
        name = rule.name
        if name.lower() not in CONTROL_RULE_NAMES and not name.lower().startswith("main"):
            het = _cost_stmt(rule.body)
            event_het[name] = het
            event_het[name.lower()] = het
    return event_het


# ============================================================================
# Term complexity: C_term
# ============================================================================

def _cost_term(term: Term) -> int:
    """Compute C_term for a term expression."""
    if isinstance(term, LiteralTerm):
        return 1

    if isinstance(term, VariableTerm):
        return 1

    if isinstance(term, LocationTerm):
        if not term.arguments:
            return 1
        return 1 + sum(_cost_term(a) for a in term.arguments)

    if isinstance(term, BinaryOpTerm):
        op = term.operator
        if op in ("and", "or"):
            return 1 + _cost_term(term.left) + _cost_term(term.right)
        if op in ("==", "!=", "<", ">", "<=", ">="):
            return 1 + _cost_term(term.left) + _cost_term(term.right)
        return 1 + _cost_term(term.left) + _cost_term(term.right)

    if isinstance(term, UnaryOpTerm):
        if term.operator == "not":
            return 1 + _cost_term(term.operand)
        return 1 + _cost_term(term.operand)

    if isinstance(term, NewTerm):
        return 1 + 1 + 1  # allocation overhead = 3

    if isinstance(term, ListTerm):
        if not term.elements:
            return 1
        return 1 + sum(_cost_term(e) for e in term.elements)

    if isinstance(term, TupleTerm):
        return 1 + sum(_cost_term(e) for e in term.elements)

    if isinstance(term, LibCallTerm):
        return 1 + sum(_cost_term(a) for a in term.arguments) + 2  # dispatch overhead

    if isinstance(term, RndCallTerm):
        return 1 + sum(_cost_term(a) for a in term.arguments)

    return 1


# ============================================================================
# Formula complexity: C_formula (applied to condition terms)
# ============================================================================

def _cost_formula(term: Term) -> int:
    """
    Compute C_formula for a Boolean condition.

    For terms used as conditions in if/while/forall guards,
    the cost is computed using formula rules:
    - Atomic comparison: 1 + C_term(t1) + C_term(t2)
    - Logical connective: 1 + C_formula(left) + C_formula(right)
    - not: 1 + C_formula(operand)
    """
    if isinstance(term, BinaryOpTerm):
        if term.operator in ("and", "or"):
            return 1 + _cost_formula(term.left) + _cost_formula(term.right)
        if term.operator in ("==", "!=", "<", ">", "<=", ">="):
            return 1 + _cost_term(term.left) + _cost_term(term.right)
        return _cost_term(term)

    if isinstance(term, UnaryOpTerm) and term.operator == "not":
        return 1 + _cost_formula(term.operand)

    return _cost_term(term)


# ============================================================================
# Rule complexity: C_rule (applied to statements)
# ============================================================================

def _cost_stmt(stmt: Stmt) -> int:
    """Compute C_rule for a statement."""
    if isinstance(stmt, SkipStmt):
        return 0

    if isinstance(stmt, UpdateStmt):
        lhs_cost = 1 + sum(_cost_term(a) for a in stmt.location.arguments)  # +1 for function symbol
        rhs_cost = _cost_term(stmt.value)
        return 1 + lhs_cost + rhs_cost

    if isinstance(stmt, SeqStmt):
        return 1 + sum(_cost_stmt(s) for s in stmt.statements)

    if isinstance(stmt, IfStmt):
        cost = 1 + _cost_formula(stmt.condition) + _cost_stmt(stmt.then_body)
        for cond, body in stmt.elseif_branches:
            cost += 1 + _cost_formula(cond) + _cost_stmt(body)
        if stmt.else_body is not None:
            cost += _cost_stmt(stmt.else_body)
        return cost

    if isinstance(stmt, LetStmt):
        return 1 + _cost_term(stmt.value)

    if isinstance(stmt, ParStmt):
        return _cost_stmt(stmt.body)

    if isinstance(stmt, ForallStmt):
        body_cost = _cost_stmt(stmt.body)
        return body_cost

    if isinstance(stmt, WhileStmt):
        return _cost_formula(stmt.condition) + _cost_stmt(stmt.body)

    if isinstance(stmt, ChooseStmt):
        return _cost_stmt(stmt.body)

    if isinstance(stmt, RuleCallStmt):
        return 1

    if isinstance(stmt, LibCallStatement):
        return 1 + sum(_cost_term(a) for a in stmt.arguments) + 2  # dispatch overhead

    if isinstance(stmt, RndCallStatement):
        return 1 + sum(_cost_term(a) for a in stmt.arguments)

    if isinstance(stmt, PrintStmt):
        return 0

    return 0
