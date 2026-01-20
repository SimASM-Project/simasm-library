"""
parser/ast.py

AST node classes for SimASM program declarations.

Contains:
- Type expressions (simple, parameterized)
- Declarations (import, domain, const, var, functions, rules)
- Program (complete parsed file)
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Any

from simasm.core.rules import Stmt
from simasm.core.terms import Term


# ============================================================================
# Type Expressions
# ============================================================================

@dataclass(frozen=True)
class TypeExpr:
    """Base class for type expressions."""
    pass


@dataclass(frozen=True)
class SimpleType(TypeExpr):
    """
    Simple type reference.
    
    Examples: Int, Real, Bool, Load, Event
    """
    name: str
    
    def __repr__(self) -> str:
        return f"Type({self.name})"


@dataclass(frozen=True)
class ParamType(TypeExpr):
    """
    Parameterized type.

    Examples: List<Event>, List<List<Int>>
    """
    name: str
    param: TypeExpr

    def __repr__(self) -> str:
        return f"Type({self.name}<{self.param}>)"


@dataclass(frozen=True)
class RndStreamType(TypeExpr):
    """
    Random stream type for stream variables.

    Syntax: rnd.distribution(params) [as "stream_name"]
    Examples:
        rnd.exponential(iat_mean)
        rnd.uniform(0, 100)
        rnd.exponential(iat_mean) as "arrivals"

    When a variable is declared with this type, each access
    draws a new random value from the specified distribution.

    The optional stream_name allows different models to share
    the same random stream by using matching names.
    """
    distribution: str  # e.g., "exponential", "uniform"
    arguments: Tuple[Term, ...]  # Parameter expressions
    stream_name: Optional[str] = None  # Explicit stream name for cross-model sync

    def __repr__(self) -> str:
        args_str = ", ".join(str(a) for a in self.arguments)
        if self.stream_name:
            return f"RndStream({self.distribution}({args_str}) as \"{self.stream_name}\")"
        return f"RndStream({self.distribution}({args_str}))"


# ============================================================================
# Parameters
# ============================================================================

@dataclass(frozen=True)
class Param:
    """
    Function/rule parameter.
    
    Example: load: Load, e: Event
    """
    name: str
    type_expr: TypeExpr
    
    def __repr__(self) -> str:
        return f"{self.name}: {self.type_expr}"


# ============================================================================
# Declarations
# ============================================================================

@dataclass(frozen=True)
class Decl:
    """Base class for all declarations."""
    pass


@dataclass(frozen=True)
class ImportDecl(Decl):
    """
    Import declaration.
    
    Syntax: import Module as alias
    Example: import Random as rnd
    """
    module: str
    alias: str
    
    def __repr__(self) -> str:
        return f"Import({self.module} as {self.alias})"


@dataclass(frozen=True)
class DomainDecl(Decl):
    """
    Domain declaration.
    
    Syntax: 
        domain Name
        domain Child <: Parent
    
    Examples:
        domain Load
        domain ArriveEvent <: Event
    """
    name: str
    parent: Optional[str] = None  # None for simple domain
    
    def __repr__(self) -> str:
        if self.parent:
            return f"Domain({self.name} <: {self.parent})"
        return f"Domain({self.name})"


@dataclass(frozen=True)
class ConstDecl(Decl):
    """
    Constant declaration.
    
    Syntax: const name: Type
    Example: const queue: Queue
    """
    name: str
    type_expr: TypeExpr
    
    def __repr__(self) -> str:
        return f"Const({self.name}: {self.type_expr})"


@dataclass(frozen=True)
class VarDecl(Decl):
    """
    Variable declaration.
    
    Syntax: var name: Type
    Example: var sim_clocktime: Real
    """
    name: str
    type_expr: TypeExpr
    
    def __repr__(self) -> str:
        return f"Var({self.name}: {self.type_expr})"


@dataclass(frozen=True)
class StaticFuncDecl(Decl):
    """
    Static function declaration.
    
    Syntax: static function name(params): Type
    Example: static function id(obj: Object): Nat
    """
    name: str
    params: Tuple[Param, ...]
    return_type: TypeExpr
    
    def __repr__(self) -> str:
        params_str = ", ".join(str(p) for p in self.params)
        return f"StaticFunc({self.name}({params_str}): {self.return_type})"


@dataclass(frozen=True)
class DynamicFuncDecl(Decl):
    """
    Dynamic function declaration.
    
    Syntax: dynamic function name(params): Type
    Example: dynamic function queues(q: Queue): List<Load>
    """
    name: str
    params: Tuple[Param, ...]
    return_type: TypeExpr
    
    def __repr__(self) -> str:
        params_str = ", ".join(str(p) for p in self.params)
        return f"DynamicFunc({self.name}({params_str}): {self.return_type})"


@dataclass(frozen=True)
class DerivedFuncDecl(Decl):
    """
    Derived function declaration.
    
    Syntax: derived function name(params): Type = expr
    Example: derived function queue_length(): Nat = lib.length(queue)
    """
    name: str
    params: Tuple[Param, ...]
    return_type: TypeExpr
    body: Term  # The expression that computes the value
    
    def __repr__(self) -> str:
        params_str = ", ".join(str(p) for p in self.params)
        return f"DerivedFunc({self.name}({params_str}): {self.return_type} = ...)"


@dataclass(frozen=True)
class RuleDecl(Decl):
    """
    Rule declaration.
    
    Syntax: rule name(params) = body endrule
    Example: rule arrive() = ... endrule
    """
    name: str
    params: Tuple[Param, ...]
    body: Stmt
    
    def __repr__(self) -> str:
        params_str = ", ".join(str(p) for p in self.params)
        return f"Rule({self.name}({params_str}) = ...)"


@dataclass(frozen=True)
class MainRuleDecl(Decl):
    """
    Main rule declaration.
    
    Syntax: main rule name = body endrule
    Example: main rule main = ... endrule
    """
    name: str
    body: Stmt
    
    def __repr__(self) -> str:
        return f"MainRule({self.name} = ...)"


@dataclass(frozen=True)
class InitBlock(Decl):
    """
    Initialization block.
    
    Syntax: init: body endinit
    Example: init: sim_clocktime := 0.0 endinit
    """
    body: Stmt
    
    def __repr__(self) -> str:
        return f"Init(...)"


# ============================================================================
# Program
# ============================================================================

@dataclass
class Program:
    """
    Complete SimASM program.
    
    Contains all declarations parsed from a .simasm file.
    """
    imports: List[ImportDecl] = field(default_factory=list)
    domains: List[DomainDecl] = field(default_factory=list)
    constants: List[ConstDecl] = field(default_factory=list)
    variables: List[VarDecl] = field(default_factory=list)
    static_funcs: List[StaticFuncDecl] = field(default_factory=list)
    dynamic_funcs: List[DynamicFuncDecl] = field(default_factory=list)
    derived_funcs: List[DerivedFuncDecl] = field(default_factory=list)
    rules: List[RuleDecl] = field(default_factory=list)
    main_rule: Optional[MainRuleDecl] = None
    init: Optional[InitBlock] = None
    
    def __repr__(self) -> str:
        parts = []
        if self.imports:
            parts.append(f"{len(self.imports)} imports")
        if self.domains:
            parts.append(f"{len(self.domains)} domains")
        if self.constants:
            parts.append(f"{len(self.constants)} constants")
        if self.variables:
            parts.append(f"{len(self.variables)} variables")
        if self.static_funcs:
            parts.append(f"{len(self.static_funcs)} static funcs")
        if self.dynamic_funcs:
            parts.append(f"{len(self.dynamic_funcs)} dynamic funcs")
        if self.derived_funcs:
            parts.append(f"{len(self.derived_funcs)} derived funcs")
        if self.rules:
            parts.append(f"{len(self.rules)} rules")
        if self.main_rule:
            parts.append("main rule")
        if self.init:
            parts.append("init")
        return f"Program({', '.join(parts)})"
