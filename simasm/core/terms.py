"""
core/terms.py

Term evaluation for SimASM.

This module provides:
- Environment: Lexical scoping for let bindings and rule parameters
- Term AST: Expression node hierarchy
- TermEvaluator: Evaluates terms to values
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from simasm.log.logger import get_logger
from .state import ASMState, ASMObject, Location, UNDEF
from .types import TypeRegistry

if TYPE_CHECKING:
    from simasm.runtime.stdlib import StandardLibrary

logger = get_logger(__name__)


# ============================================================================
# Environment - Lexical Scoping
# ============================================================================

class Environment:
    """
    Variable bindings with lexical scoping.
    
    Used for:
    - Rule parameters
    - Let bindings
    - Forall loop variables
    
    Scoping rules:
    - Child scopes can see parent bindings
    - Child bindings shadow parent bindings
    - Bindings are mutable within their scope
    
    Usage:
        env = Environment()
        env.bind("x", 10)
        
        # Child scope
        child = env.child()
        child.bind("y", 20)
        child.lookup("x")  # 10 (from parent)
        child.lookup("y")  # 20 (from child)
        
        # Shadowing
        child.bind("x", 99)
        child.lookup("x")  # 99 (shadowed)
        env.lookup("x")    # 10 (unchanged in parent)
    """
    
    def __init__(self, parent: Optional['Environment'] = None):
        self._parent = parent
        self._bindings: Dict[str, Any] = {}
    
    def bind(self, name: str, value: Any) -> None:
        """
        Bind name to value in this scope.
        
        Args:
            name: Variable name
            value: Value to bind
        """
        self._bindings[name] = value
        logger.debug(f"Bound {name} = {value!r}")
    
    def rebind(self, name: str, value: Any) -> None:
        """
        Rebind existing name to new value.
        
        Searches up the scope chain to find where name is bound,
        then updates that binding.
        
        Args:
            name: Variable name (must exist)
            value: New value
            
        Raises:
            NameError: If name is not bound anywhere
        """
        if name in self._bindings:
            self._bindings[name] = value
            logger.debug(f"Rebound {name} = {value!r}")
        elif self._parent:
            self._parent.rebind(name, value)
        else:
            raise NameError(f"Cannot rebind undefined variable: {name}")
    
    def lookup(self, name: str) -> Any:
        """
        Look up name, searching parent scopes.
        
        Args:
            name: Variable name
            
        Returns:
            The bound value
            
        Raises:
            NameError: If name is not bound
        """
        if name in self._bindings:
            return self._bindings[name]
        if self._parent:
            return self._parent.lookup(name)
        raise NameError(f"Undefined variable: {name}")
    
    def contains(self, name: str) -> bool:
        """
        Check if name is bound (in this or parent scope).
        
        Args:
            name: Variable name
            
        Returns:
            True if bound somewhere in scope chain
        """
        if name in self._bindings:
            return True
        if self._parent:
            return self._parent.contains(name)
        return False
    
    def local_names(self) -> set:
        """
        Get names bound in this scope only (not parents).
        
        Returns:
            Set of locally bound names
        """
        return set(self._bindings.keys())
    
    def all_names(self) -> set:
        """
        Get all names bound in this and parent scopes.
        
        Returns:
            Set of all bound names
        """
        names = set(self._bindings.keys())
        if self._parent:
            names.update(self._parent.all_names())
        return names
    
    def child(self) -> 'Environment':
        """
        Create child scope.
        
        Returns:
            New Environment with this as parent
        """
        return Environment(parent=self)
    
    @property
    def parent(self) -> Optional['Environment']:
        """Get parent scope, or None if root."""
        return self._parent
    
    @property
    def depth(self) -> int:
        """Get scope depth (0 for root)."""
        if self._parent is None:
            return 0
        return 1 + self._parent.depth
    
    def __repr__(self) -> str:
        return f"Environment(depth={self.depth}, bindings={list(self._bindings.keys())})"


# ============================================================================
# Term AST - Expression Nodes
# ============================================================================

class Term(ABC):
    """
    Base class for all expression nodes.
    
    Terms represent expressions that can be evaluated to produce values.
    They are created by the parser and evaluated by TermEvaluator.
    
    All Term subclasses are frozen dataclasses for immutability.
    """
    pass


@dataclass(frozen=True)
class LiteralTerm(Term):
    """
    Literal value.
    
    Examples: 42, 3.14, true, false, "hello", undef
    """
    value: Any
    
    def __repr__(self) -> str:
        return f"Literal({self.value!r})"


@dataclass(frozen=True)
class VariableTerm(Term):
    """
    Variable reference from environment.
    
    Used for let-bound variables and rule parameters.
    NOT for state locations (use LocationTerm for those).
    
    Examples: x, load, counter
    """
    name: str
    
    def __repr__(self) -> str:
        return f"Var({self.name})"


@dataclass(frozen=True)
class LocationTerm(Term):
    """
    State location lookup.
    
    Used for const/var declarations and dynamic functions.
    
    Examples:
    - x (0-ary variable)
    - status(load) (1-ary function)
    - matrix(i, j) (2-ary function)
    """
    func_name: str
    arguments: Tuple['Term', ...] = ()
    
    def __repr__(self) -> str:
        if not self.arguments:
            return f"Loc({self.func_name})"
        args_str = ", ".join(repr(a) for a in self.arguments)
        return f"Loc({self.func_name}({args_str}))"


@dataclass(frozen=True)
class BinaryOpTerm(Term):
    """
    Binary operation.
    
    Operators:
    - Arithmetic: +, -, *, /, //, %
    - Comparison: ==, !=, <, >, <=, >=
    - Logical: and, or
    
    Examples: a + b, x == y, flag and ready
    """
    operator: str
    left: Term
    right: Term
    
    def __repr__(self) -> str:
        return f"BinOp({self.left!r} {self.operator} {self.right!r})"


@dataclass(frozen=True)
class UnaryOpTerm(Term):
    """
    Unary operation.
    
    Operators:
    - Arithmetic: - (negation)
    - Logical: not
    
    Examples: -x, not flag
    """
    operator: str
    operand: Term
    
    def __repr__(self) -> str:
        return f"UnaryOp({self.operator} {self.operand!r})"


@dataclass(frozen=True)
class ListTerm(Term):
    """
    List literal.
    
    Examples: [], [1, 2, 3], [load1, load2]
    """
    elements: Tuple[Term, ...]
    
    def __repr__(self) -> str:
        if not self.elements:
            return "List([])"
        elems_str = ", ".join(repr(e) for e in self.elements)
        return f"List([{elems_str}])"


@dataclass(frozen=True)
class TupleTerm(Term):
    """
    Tuple literal.
    
    Examples: (x, y), (vertex, time, priority)
    """
    elements: Tuple[Term, ...]
    
    def __repr__(self) -> str:
        elems_str = ", ".join(repr(e) for e in self.elements)
        return f"Tuple(({elems_str}))"


@dataclass(frozen=True)
class NewTerm(Term):
    """
    Object creation expression.
    
    Creates a new ASMObject of the given domain.
    
    Examples: new Load, new Event
    """
    domain: str
    
    def __repr__(self) -> str:
        return f"New({self.domain})"


@dataclass(frozen=True)
class LibCallTerm(Term):
    """
    Library function call.
    
    Calls a function from StandardLibrary.
    May return a value or None.
    
    Examples: lib.length(queue), lib.add(queue, item)
    """
    func_name: str
    arguments: Tuple[Term, ...]
    
    def __repr__(self) -> str:
        args_str = ", ".join(repr(a) for a in self.arguments)
        return f"LibCall(lib.{self.func_name}({args_str}))"


@dataclass(frozen=True)
class RndCallTerm(Term):
    """
    Random number generator call.
    
    Calls a function from RandomGenerator.
    
    Examples: 
    - rnd.exponential(1.0) - default stream
    - rnd.arrivals.exponential(2.0) - named stream
    """
    func_name: str
    arguments: Tuple[Term, ...]
    stream: Optional[str] = None  # None = default stream
    
    def __repr__(self) -> str:
        args_str = ", ".join(repr(a) for a in self.arguments)
        if self.stream:
            return f"RndCall(rnd.{self.stream}.{self.func_name}({args_str}))"
        return f"RndCall(rnd.{self.func_name}({args_str}))"


@dataclass(frozen=True)
class ConditionalTerm(Term):
    """
    Conditional expression (ternary).
    
    Evaluates condition, returns then_expr if true, else_expr if false.
    
    Example: if x > 0 then x else -x
    """
    condition: Term
    then_expr: Term
    else_expr: Term
    
    def __repr__(self) -> str:
        return f"Cond(if {self.condition!r} then {self.then_expr!r} else {self.else_expr!r})"


# ============================================================================
# TermEvaluator
# ============================================================================

class TermEvaluationError(Exception):
    """Raised when term evaluation fails."""
    pass


class TermEvaluator:
    """
    Evaluates Term nodes against ASM state.
    
    Usage:
        evaluator = TermEvaluator(state, types)
        evaluator.set_stdlib(stdlib)  # After stdlib is created
        
        env = Environment()
        env.bind("x", 10)
        
        term = BinaryOpTerm("+", VariableTerm("x"), LiteralTerm(5))
        result = evaluator.eval(term, env)  # 15
    """
    
    # Supported binary operators
    BINARY_OPS = {
        # Arithmetic
        '+': lambda a, b: a + b,
        '-': lambda a, b: a - b,
        '*': lambda a, b: a * b,
        '/': lambda a, b: a / b,
        '//': lambda a, b: a // b,
        '%': lambda a, b: a % b,
        # Comparison
        '==': lambda a, b: a == b,
        '!=': lambda a, b: a != b,
        '<': lambda a, b: a < b,
        '>': lambda a, b: a > b,
        '<=': lambda a, b: a <= b,
        '>=': lambda a, b: a >= b,
        # Logical
        'and': lambda a, b: a and b,
        'or': lambda a, b: a or b,
    }
    
    # Supported unary operators
    UNARY_OPS = {
        '-': lambda a: -a,
        'not': lambda a: not a,
    }
    
    def __init__(self, state: ASMState, types: TypeRegistry,
                 stdlib: Optional['StandardLibrary'] = None,
                 rng: Optional[Any] = None):
        """
        Create evaluator.
        
        Args:
            state: ASM state for location lookups
            types: Type registry for domain validation
            stdlib: Standard library (can be set later via set_stdlib)
            rng: Random number generator (can be set later via set_rng)
        """
        self._state = state
        self._types = types
        self._stdlib = stdlib
        self._rng = rng
        self._derived_funcs: Dict[str, Any] = {}  # name -> DerivedFuncDecl
        self._stream_vars: Dict[str, Any] = {}  # name -> RndStreamType
    
    def set_stdlib(self, stdlib: 'StandardLibrary') -> None:
        """Set standard library (for lib.* calls)."""
        self._stdlib = stdlib
    
    def set_rng(self, rng: Any) -> None:
        """Set random number generator (for rnd.* calls)."""
        self._rng = rng
    
    def set_derived_funcs(self, derived_funcs: Dict[str, Any]) -> None:
        """Set derived functions (for computed function calls)."""
        self._derived_funcs = derived_funcs

    def set_stream_vars(self, stream_vars: Dict[str, Any]) -> None:
        """Set stream variables (var name: rnd.distribution(args))."""
        self._stream_vars = stream_vars
    
    @property
    def state(self) -> ASMState:
        """Get the ASM state."""
        return self._state
    
    @property
    def types(self) -> TypeRegistry:
        """Get the type registry."""
        return self._types
    
    def eval(self, term: Term, env: Environment) -> Any:
        """
        Evaluate term in given environment.
        
        Args:
            term: The term to evaluate
            env: Environment for variable lookups
            
        Returns:
            The computed value
            
        Raises:
            TermEvaluationError: If evaluation fails
        """
        logger.debug(f"Evaluating: {term!r}")
        
        if isinstance(term, LiteralTerm):
            return self._eval_literal(term)
        elif isinstance(term, VariableTerm):
            return self._eval_variable(term, env)
        elif isinstance(term, LocationTerm):
            return self._eval_location(term, env)
        elif isinstance(term, BinaryOpTerm):
            return self._eval_binary(term, env)
        elif isinstance(term, UnaryOpTerm):
            return self._eval_unary(term, env)
        elif isinstance(term, ListTerm):
            return self._eval_list(term, env)
        elif isinstance(term, TupleTerm):
            return self._eval_tuple(term, env)
        elif isinstance(term, NewTerm):
            return self._eval_new(term)
        elif isinstance(term, LibCallTerm):
            return self._eval_libcall(term, env)
        elif isinstance(term, RndCallTerm):
            return self._eval_rndcall(term, env)
        elif isinstance(term, ConditionalTerm):
            return self._eval_conditional(term, env)
        else:
            raise TermEvaluationError(f"Unknown term type: {type(term).__name__}")
    
    def eval_with_state(self, term: Term, env: Environment, state: ASMState) -> Any:
        """
        Evaluate term against a specific state (not self._state).
        
        Useful for verification where labeling functions are evaluated
        against evolving stepper state, not the original loaded state.
        
        Args:
            term: The term to evaluate
            env: Environment for variable lookups
            state: The state to evaluate against (temporary override)
            
        Returns:
            The computed value
        """
        old_state = self._state
        self._state = state
        try:
            return self.eval(term, env)
        finally:
            self._state = old_state
    
    def _eval_literal(self, term: LiteralTerm) -> Any:
        """Evaluate literal - just return its value."""
        return term.value
    
    def _eval_variable(self, term: VariableTerm, env: Environment) -> Any:
        """
        Evaluate variable - look up in environment, stream vars, then state.

        Order of lookup:
        1. Environment (let bindings, rule parameters)
        2. Stream variables (var name: rnd.distribution(args)) - draws new value
        3. State (0-ary dynamic functions / state variables)
        """
        # First try environment
        if env.contains(term.name):
            return env.lookup(term.name)

        # Check if this is a stream variable - draw new random value
        if term.name in self._stream_vars:
            return self._eval_stream_var(term.name, env)

        # Fall back to state (0-ary location)
        loc = Location(term.name, ())
        value = self._state.get(loc)
        if value is not UNDEF:
            return value

        # Not found anywhere
        raise TermEvaluationError(f"Undefined variable: {term.name}")

    def _eval_stream_var(self, name: str, env: Environment) -> Any:
        """
        Evaluate stream variable - draw new random value each time.

        Stream variables are declared as: var name: rnd.distribution(args) [as "stream_name"]
        Each access calls the distribution function to get a new value.

        If an explicit stream_name is provided (via 'as "name"'), that name is used
        for the random stream. Otherwise, the variable name is used. This allows
        different models to share the same random streams by using matching names.
        """
        stream_type = self._stream_vars[name]
        distribution = stream_type.distribution

        # Evaluate arguments (they may reference other variables)
        args = [self.eval(arg, env) for arg in stream_type.arguments]

        # Use explicit stream name if provided, otherwise use variable name
        stream_name = stream_type.stream_name if stream_type.stream_name else name
        rng = self._rng.stream(stream_name)

        # Call the distribution function
        if not hasattr(rng, distribution):
            raise TermEvaluationError(
                f"Unknown distribution '{distribution}' for stream variable '{name}'"
            )

        func = getattr(rng, distribution)
        result = func(*args)
        logger.debug(f"Stream var '{name}' (stream={stream_name}): {distribution}({args}) = {result}")
        return result
    
    def _eval_location(self, term: LocationTerm, env: Environment) -> Any:
        """Evaluate location - evaluate args, then look up in state or derived func."""
        # Evaluate arguments
        args = tuple(self.eval(arg, env) for arg in term.arguments)
        
        # Check if this is a derived function (0-ary function with matching name)
        if len(args) == 0 and term.func_name in self._derived_funcs:
            # Evaluate derived function body
            derived_decl = self._derived_funcs[term.func_name]
            return self.eval(derived_decl.body, env)
        
        # Look up in state
        loc = Location(term.func_name, args)
        return self._state.get(loc)
    
    def _eval_binary(self, term: BinaryOpTerm, env: Environment) -> Any:
        """Evaluate binary operation."""
        op = term.operator
        
        if op not in self.BINARY_OPS:
            raise TermEvaluationError(f"Unknown binary operator: {op}")
        
        # Short-circuit for logical operators
        if op == 'and':
            left_val = self.eval(term.left, env)
            if not left_val:
                return False
            return bool(self.eval(term.right, env))
        
        if op == 'or':
            left_val = self.eval(term.left, env)
            if left_val:
                return True
            return bool(self.eval(term.right, env))
        
        # Standard evaluation
        left_val = self.eval(term.left, env)
        right_val = self.eval(term.right, env)
        
        try:
            return self.BINARY_OPS[op](left_val, right_val)
        except TypeError as e:
            raise TermEvaluationError(
                f"Type error in {left_val!r} {op} {right_val!r}: {e}"
            ) from e
        except ZeroDivisionError as e:
            raise TermEvaluationError(f"Division by zero: {term}") from e
    
    def _eval_unary(self, term: UnaryOpTerm, env: Environment) -> Any:
        """Evaluate unary operation."""
        op = term.operator
        
        if op not in self.UNARY_OPS:
            raise TermEvaluationError(f"Unknown unary operator: {op}")
        
        operand_val = self.eval(term.operand, env)
        
        try:
            return self.UNARY_OPS[op](operand_val)
        except TypeError as e:
            raise TermEvaluationError(
                f"Type error in {op} {operand_val!r}: {e}"
            ) from e
    
    def _eval_list(self, term: ListTerm, env: Environment) -> list:
        """Evaluate list literal - evaluate each element."""
        return [self.eval(elem, env) for elem in term.elements]
    
    def _eval_tuple(self, term: TupleTerm, env: Environment) -> tuple:
        """Evaluate tuple literal - evaluate each element."""
        return tuple(self.eval(elem, env) for elem in term.elements)
    
    def _eval_new(self, term: NewTerm) -> ASMObject:
        """Evaluate new expression - create ASMObject."""
        domain = term.domain
        
        # Validate domain exists
        if not self._types.exists(domain):
            raise TermEvaluationError(f"Unknown domain: {domain}")
        
        obj = ASMObject(domain)
        logger.debug(f"Created new object: {obj}")
        return obj
    
    def _eval_libcall(self, term: LibCallTerm, env: Environment) -> Any:
        """Evaluate library call."""
        if self._stdlib is None:
            raise TermEvaluationError("Standard library not set")
        
        func_name = term.func_name
        
        # Check if function exists
        if not hasattr(self._stdlib, func_name):
            raise TermEvaluationError(f"Unknown library function: lib.{func_name}")
        
        # Evaluate arguments
        args = [self.eval(arg, env) for arg in term.arguments]
        
        # Call function
        func = getattr(self._stdlib, func_name)
        try:
            result = func(*args)
            logger.debug(f"lib.{func_name}({args}) = {result!r}")
            return result
        except Exception as e:
            raise TermEvaluationError(
                f"Error calling lib.{func_name}: {e}"
            ) from e
    
    def _eval_rndcall(self, term: RndCallTerm, env: Environment) -> Any:
        """Evaluate random number generator call."""
        if self._rng is None:
            raise TermEvaluationError("Random generator not set")
        
        func_name = term.func_name
        stream = term.stream
        
        # Evaluate arguments
        args = [self.eval(arg, env) for arg in term.arguments]
        
        # Get the appropriate stream
        if stream:
            rng = self._rng.stream(stream)
        else:
            rng = self._rng
        
        # Check if function exists
        if not hasattr(rng, func_name):
            raise TermEvaluationError(f"Unknown random function: rnd.{func_name}")
        
        # Call function
        func = getattr(rng, func_name)
        try:
            result = func(*args)
            if stream:
                logger.debug(f"rnd.{stream}.{func_name}({args}) = {result!r}")
            else:
                logger.debug(f"rnd.{func_name}({args}) = {result!r}")
            return result
        except Exception as e:
            raise TermEvaluationError(
                f"Error calling rnd.{func_name}: {e}"
            ) from e
    
    def _eval_conditional(self, term: ConditionalTerm, env: Environment) -> Any:
        """Evaluate conditional expression."""
        cond_val = self.eval(term.condition, env)
        
        if cond_val:
            return self.eval(term.then_expr, env)
        else:
            return self.eval(term.else_expr, env)