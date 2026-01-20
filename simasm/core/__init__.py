"""
SimASM core module.

Contains fundamental ASM constructs:
- types: Domain and type hierarchy
- state: ASM state representation
- update: Update and UpdateSet
- terms: Term/expression evaluation
- rules: Rule evaluation
"""

from .types import Domain, TypeRegistry, BUILTIN_TYPES
from .state import UNDEF, Undefined, ASMObject, Location, ASMState
from .update import Update, UpdateConflictError, UpdateSet
from .terms import (
    Environment,
    Term, LiteralTerm, VariableTerm, LocationTerm,
    BinaryOpTerm, UnaryOpTerm, ListTerm, TupleTerm, NewTerm,
    LibCallTerm, RndCallTerm, ConditionalTerm,
    TermEvaluator, TermEvaluationError,
)
from .rules import (
    Stmt, SkipStmt, UpdateStmt, SeqStmt, IfStmt,
    WhileStmt, ForallStmt, LetStmt, RuleCallStmt, PrintStmt,
    ChooseStmt, ParStmt, LibCallStmt, RndCallStmt,
    RuleDefinition, RuleRegistry,
    RuleEvaluator, RuleEvaluatorConfig,
    RuleEvaluationError, InfiniteLoopError, MaxRecursionError,
)

__all__ = [
    # types
    'Domain', 'TypeRegistry', 'BUILTIN_TYPES',
    # state
    'UNDEF', 'Undefined', 'ASMObject', 'Location', 'ASMState',
    # update
    'Update', 'UpdateConflictError', 'UpdateSet',
    # terms
    'Environment',
    'Term', 'LiteralTerm', 'VariableTerm', 'LocationTerm',
    'BinaryOpTerm', 'UnaryOpTerm', 'ListTerm', 'TupleTerm', 'NewTerm',
    'LibCallTerm', 'RndCallTerm', 'ConditionalTerm',
    'TermEvaluator', 'TermEvaluationError',
    # rules
    'Stmt', 'SkipStmt', 'UpdateStmt', 'SeqStmt', 'IfStmt',
    'WhileStmt', 'ForallStmt', 'LetStmt', 'RuleCallStmt', 'PrintStmt',
    'ChooseStmt', 'ParStmt', 'LibCallStmt', 'RndCallStmt',
    'RuleDefinition', 'RuleRegistry',
    'RuleEvaluator', 'RuleEvaluatorConfig',
    'RuleEvaluationError', 'InfiniteLoopError', 'MaxRecursionError',
]
