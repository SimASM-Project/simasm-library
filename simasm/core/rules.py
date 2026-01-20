"""
core/rules.py

Rule definition and evaluation for SimASM.

Contains:
- Statement AST nodes (SkipStmt, UpdateStmt, IfStmt, WhileStmt, etc.)
- RuleDefinition: Named rule with parameters and body
- RuleRegistry: Collection of all rules
- RuleEvaluator: Executes statements, produces UpdateSets
"""

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable

from simasm.log.logger import get_logger
from .state import ASMState, ASMObject, Location, UNDEF
from .update import Update, UpdateSet, UpdateConflictError
from .terms import (
    Term, LiteralTerm, VariableTerm, LocationTerm,
    Environment, TermEvaluator
)

logger = get_logger(__name__)


# ============================================================================
# Statement AST Nodes
# ============================================================================

class Stmt(ABC):
    """Base class for all statement nodes."""
    pass


@dataclass(frozen=True)
class SkipStmt(Stmt):
    """
    Skip statement - does nothing.
    
    Syntax: skip
    Produces empty UpdateSet.
    
    Example:
        if condition then
            do_something()
        else
            skip
        endif
    """
    pass


@dataclass(frozen=True)
class UpdateStmt(Stmt):
    """
    Assignment statement.
    
    Syntax: location := value
    
    Examples:
        x := 10
        status(load) := "waiting"
        queues(queue) := [load1, load2]
    """
    location: LocationTerm  # LHS - where to store
    value: Term             # RHS - what to store
    
    def __repr__(self) -> str:
        return f"UpdateStmt({self.location} := {self.value})"


@dataclass(frozen=True)
class SeqStmt(Stmt):
    """
    Sequence of statements (executed in order).
    
    Default execution mode - statements on consecutive lines.
    Each statement sees effects of previous statements (sequential semantics).
    
    Example:
        x := 1
        y := x + 1    // y becomes 2
    """
    statements: Tuple[Stmt, ...]
    
    def __repr__(self) -> str:
        return f"SeqStmt({len(self.statements)} statements)"


@dataclass(frozen=True)
class IfStmt(Stmt):
    """
    Conditional statement.
    
    Supports:
    - Simple if/then/endif
    - if/then/else/endif
    - Multiple elseif branches
    - Nested if statements
    
    Syntax:
        if cond then body endif
        if cond then body else body endif
        if cond then body elseif cond then body else body endif
    
    Example:
        if x == 1 then
            result := "one"
        elseif x == 2 then
            result := "two"
        else
            result := "other"
        endif
    """
    condition: Term
    then_body: Stmt
    elseif_branches: Tuple[Tuple[Term, Stmt], ...] = ()  # [(cond, body), ...]
    else_body: Optional[Stmt] = None
    
    def __repr__(self) -> str:
        parts = ["IfStmt("]
        parts.append(f"if {self.condition}")
        if self.elseif_branches:
            parts.append(f", {len(self.elseif_branches)} elseif")
        if self.else_body:
            parts.append(", else")
        parts.append(")")
        return "".join(parts)


@dataclass(frozen=True)
class WhileStmt(Stmt):
    """
    While loop - all iterations execute in ONE ASM step.
    
    Syntax: while cond do body endwhile
    
    Sequential semantics:
    - Condition re-evaluated after each iteration on updated state
    - Loop variable changes visible to next iteration
    
    Example:
        while lib.length(queue) > 0 and server_available() do
            process_next()
        endwhile
    
    Warning: Infinite loops will raise InfiniteLoopError after max iterations.
    """
    condition: Term
    body: Stmt
    
    def __repr__(self) -> str:
        return f"WhileStmt(while {self.condition} do ...)"


@dataclass(frozen=True)
class ForallStmt(Stmt):
    """
    Forall iteration over collection with optional guard.
    
    Syntax: 
        forall x in collection do body endforall
        forall x in collection with condition do body endforall
    
    Parallel semantics:
    - All iterations see ORIGINAL state (not effects of other iterations)
    - Updates from all iterations are merged
    - Conflicting updates (same location, different values) raise error
    
    Examples:
        // Without guard
        forall e in OutEdges(v) do
            schedule_event(target(e), delay(e))
        endforall
        
        // With guard (only edges where condition is true)
        forall e in OutEdges(v) with edge_enabled(e) do
            schedule_event(target(e), delay(e))
        endforall
    
    Note: Use 'while' if iterations need to see effects of previous iterations.
    """
    var_name: str
    collection: Term
    body: Stmt
    guard: Optional[Term] = None  # Optional: "with condition"
    
    def __repr__(self) -> str:
        guard_str = f" with guard" if self.guard else ""
        return f"ForallStmt(forall {self.var_name} in {self.collection}{guard_str} do ...)"


@dataclass(frozen=True)
class LetStmt(Stmt):
    """
    Let binding - binds variable in current scope.
    
    Syntax: let x = expr
    
    Scope extends to end of enclosing block/rule.
    Does NOT produce any updates - only modifies environment.
    
    Example:
        let load = new Load
        id(load) := load_id
        status(load) := "arrived"
    """
    var_name: str
    value: Term
    
    def __repr__(self) -> str:
        return f"LetStmt(let {self.var_name} = {self.value})"


@dataclass(frozen=True)
class RuleCallStmt(Stmt):
    """
    Rule invocation.
    
    Syntax: rule_name(arg1, arg2, ...)
    
    Updates from called rule are merged into caller's UpdateSet.
    Supports dynamic dispatch when rule_name is a LocationTerm.
    
    Examples:
        arrive()                          // No arguments
        start(load)                       // With argument
        lib.apply_rule(event_rule(e), params)  // Dynamic dispatch
    """
    rule_name: Term  # Can be VariableTerm/LiteralTerm for static, LocationTerm for dynamic
    arguments: Tuple[Term, ...] = ()
    
    def __repr__(self) -> str:
        args = ", ".join(str(a) for a in self.arguments)
        return f"RuleCallStmt({self.rule_name}({args}))"


@dataclass(frozen=True)
class PrintStmt(Stmt):
    """
    Debug print statement.
    
    Syntax: print(expr)
    
    Prints value to console or configured callback.
    Does NOT produce any updates.
    
    Example:
        print(sim_clocktime)
        print("Processing load")
        print(lib.length(queue))
    """
    expression: Term
    
    def __repr__(self) -> str:
        return f"PrintStmt(print({self.expression}))"


@dataclass(frozen=True)
class ChooseStmt(Stmt):
    """
    Nondeterministic choice from collection with optional guard.
    
    Syntax:
        choose x in collection do body endchoose
        choose x in collection with condition do body endchoose
    
    Selects ONE element nondeterministically (typically first matching).
    If no elements match, body is not executed.
    
    Example:
        choose server in servers with not busy(server) do
            assign(load, server)
        endchoose
    """
    var_name: str
    collection: Term
    body: Stmt
    guard: Optional[Term] = None
    
    def __repr__(self) -> str:
        guard_str = f" with guard" if self.guard else ""
        return f"ChooseStmt(choose {self.var_name} in {self.collection}{guard_str} do ...)"


@dataclass(frozen=True)
class ParStmt(Stmt):
    """
    Parallel block - all statements execute on ORIGINAL state.
    
    Syntax: par stmts endpar
    
    Unlike sequential execution:
    - All statements see the same initial state
    - Updates are merged at the end
    - Conflicting updates raise error
    
    Example:
        par
            x := y    // Both see original values
            y := x    // Swap in parallel
        endpar
    """
    body: Stmt  # Usually a SeqStmt containing multiple statements
    
    def __repr__(self) -> str:
        return f"ParStmt(par ... endpar)"


@dataclass(frozen=True)
class LibCallStmt(Stmt):
    """
    Library function call as statement (for side effects).
    
    Syntax: lib.func(args)
    
    Used when lib function modifies state (e.g., lib.add, lib.remove).
    Return value is discarded.
    
    Example:
        lib.add(queue, load)
        lib.remove(queue, load)
        lib.sort(fel, "1")
    """
    func_name: str
    arguments: Tuple[Term, ...]
    
    def __repr__(self) -> str:
        args = ", ".join(str(a) for a in self.arguments)
        return f"LibCallStmt(lib.{self.func_name}({args}))"


@dataclass(frozen=True)
class RndCallStmt(Stmt):
    """
    Random function call as statement (for side effects like seeding).
    
    Syntax: 
        rnd.func(args)
        rnd.stream.func(args)
    
    Example:
        rnd.seed(42)
        rnd.arrivals.seed(123)
    """
    func_name: str
    arguments: Tuple[Term, ...]
    stream: Optional[str] = None
    
    def __repr__(self) -> str:
        args = ", ".join(str(a) for a in self.arguments)
        if self.stream:
            return f"RndCallStmt(rnd.{self.stream}.{self.func_name}({args}))"
        return f"RndCallStmt(rnd.{self.func_name}({args}))"


# ============================================================================
# Rule Definition and Registry
# ============================================================================

@dataclass
class RuleDefinition:
    """
    A named rule with parameters and body.
    
    Example:
        rule arrive(load: Load) =
            status(load) := "arrived"
            queue_count := queue_count + 1
    
    Attributes:
        name: Rule name (used for invocation)
        parameters: Parameter names (types not enforced in v1.0)
        body: Rule body (None for built-in/external rules)
    """
    name: str
    parameters: Tuple[str, ...] = ()
    body: Optional[Stmt] = None
    
    def __repr__(self) -> str:
        params = ", ".join(self.parameters)
        has_body = "with body" if self.body else "no body"
        return f"RuleDefinition({self.name}({params}), {has_body})"
    
    def __str__(self) -> str:
        params = ", ".join(self.parameters)
        return f"rule {self.name}({params})"


class RuleRegistry:
    """
    Collection of all rule definitions.
    
    Usage:
        registry = RuleRegistry()
        registry.register(RuleDefinition("arrive", ("load",), body))
        rule = registry.get("arrive")
        
        if "arrive" in registry:
            ...
    """
    
    def __init__(self):
        self._rules: Dict[str, RuleDefinition] = {}
        logger.debug("Created RuleRegistry")
    
    def register(self, rule: RuleDefinition) -> None:
        """
        Register a rule definition.
        
        Raises:
            ValueError: If rule with same name already registered
        """
        if rule.name in self._rules:
            raise ValueError(f"Rule already registered: {rule.name}")
        self._rules[rule.name] = rule
        logger.debug(f"Registered rule: {rule}")
    
    def get(self, name: str) -> Optional[RuleDefinition]:
        """Get rule by name, or None if not found."""
        return self._rules.get(name)
    
    def exists(self, name: str) -> bool:
        """Check if rule exists."""
        return name in self._rules
    
    def all_rules(self) -> List[str]:
        """Return all rule names."""
        return list(self._rules.keys())
    
    def clear(self) -> None:
        """Remove all rules."""
        self._rules.clear()
        logger.debug("Cleared RuleRegistry")
    
    def __contains__(self, name: str) -> bool:
        """Check if rule exists: 'arrive' in registry"""
        return name in self._rules
    
    def __len__(self) -> int:
        """Number of registered rules."""
        return len(self._rules)
    
    def __repr__(self) -> str:
        return f"RuleRegistry({len(self._rules)} rules)"


# ============================================================================
# Rule Evaluator Exceptions
# ============================================================================

class RuleEvaluationError(Exception):
    """Raised when rule evaluation fails."""
    pass


class InfiniteLoopError(RuleEvaluationError):
    """Raised when while loop exceeds max iterations."""
    
    def __init__(self, iterations: int, max_iterations: int):
        self.iterations = iterations
        self.max_iterations = max_iterations
        super().__init__(
            f"While loop exceeded maximum iterations: {iterations} > {max_iterations}"
        )


class MaxRecursionError(RuleEvaluationError):
    """Raised when rule recursion exceeds max depth."""
    
    def __init__(self, depth: int, max_depth: int, rule_name: str):
        self.depth = depth
        self.max_depth = max_depth
        self.rule_name = rule_name
        super().__init__(
            f"Max recursion depth exceeded in rule '{rule_name}': {depth} > {max_depth}"
        )


# ============================================================================
# Rule Evaluator Configuration
# ============================================================================

@dataclass
class RuleEvaluatorConfig:
    """
    Configuration for RuleEvaluator.
    
    Attributes:
        max_while_iterations: Safety limit for while loops (default 10000)
        max_recursion_depth: Safety limit for rule recursion (default 1000)
        print_callback: Custom callback for print statements (default: print to console)
    """
    max_while_iterations: int = 10000
    max_recursion_depth: int = 1000
    print_callback: Optional[Callable[[Any], None]] = None


# ============================================================================
# Rule Evaluator
# ============================================================================

class RuleEvaluator:
    """
    Evaluates statements and produces UpdateSets.
    
    Handles all statement types:
    - SkipStmt: Returns empty UpdateSet
    - UpdateStmt: Creates update for location
    - SeqStmt: Sequential execution, applies updates immediately
    - IfStmt: Conditional branching
    - WhileStmt: Loop with all iterations in one step
    - ForallStmt: Parallel iteration, merges updates
    - LetStmt: Binds variable in environment
    - RuleCallStmt: Invokes another rule
    - PrintStmt: Debug output
    
    Usage:
        evaluator = RuleEvaluator(state, rules, term_evaluator)
        env = Environment()
        updates = evaluator.eval(stmt, env)
        # Note: For SeqStmt/WhileStmt, updates are already applied to state
    """
    
    def __init__(
        self,
        state: ASMState,
        rules: RuleRegistry,
        term_evaluator: TermEvaluator,
        config: Optional[RuleEvaluatorConfig] = None
    ):
        """
        Initialize RuleEvaluator.
        
        Args:
            state: ASM state to read/modify
            rules: Registry of rule definitions
            term_evaluator: Evaluator for terms/expressions
            config: Optional configuration (uses defaults if None)
        """
        self._state = state
        self._rules = rules
        self._term_eval = term_evaluator
        self._config = config or RuleEvaluatorConfig()
        self._recursion_depth = 0
        self._call_stack: List[str] = []  # For debugging
        logger.debug(f"Created RuleEvaluator with config: {self._config}")
    
    @property
    def state(self) -> ASMState:
        """Access to current state."""
        return self._state
    
    @property
    def rules(self) -> RuleRegistry:
        """Access to rule registry."""
        return self._rules
    
    def eval(self, stmt: Stmt, env: Environment) -> UpdateSet:
        """
        Evaluate statement in given environment.
        
        Args:
            stmt: Statement to evaluate
            env: Variable environment (let bindings, rule parameters)
        
        Returns:
            UpdateSet containing all updates produced
            
        Note: For sequential constructs (SeqStmt, WhileStmt), updates
        are applied to state during evaluation.
        """
        if isinstance(stmt, SkipStmt):
            return self._eval_skip(stmt, env)
        elif isinstance(stmt, UpdateStmt):
            return self._eval_update(stmt, env)
        elif isinstance(stmt, SeqStmt):
            return self._eval_seq(stmt, env)
        elif isinstance(stmt, IfStmt):
            return self._eval_if(stmt, env)
        elif isinstance(stmt, WhileStmt):
            return self._eval_while(stmt, env)
        elif isinstance(stmt, ForallStmt):
            return self._eval_forall(stmt, env)
        elif isinstance(stmt, ChooseStmt):
            return self._eval_choose(stmt, env)
        elif isinstance(stmt, ParStmt):
            return self._eval_par(stmt, env)
        elif isinstance(stmt, LetStmt):
            return self._eval_let(stmt, env)
        elif isinstance(stmt, RuleCallStmt):
            return self._eval_rule_call(stmt, env)
        elif isinstance(stmt, LibCallStmt):
            return self._eval_lib_call_stmt(stmt, env)
        elif isinstance(stmt, RndCallStmt):
            return self._eval_rnd_call_stmt(stmt, env)
        elif isinstance(stmt, PrintStmt):
            return self._eval_print(stmt, env)
        else:
            raise RuleEvaluationError(f"Unknown statement type: {type(stmt).__name__}")
    
    def invoke_rule(self, rule_name: str, args: List[Any], env: Environment) -> UpdateSet:
        """
        Invoke a rule by name with evaluated arguments.
        
        Args:
            rule_name: Name of rule to invoke
            args: Already-evaluated argument values
            env: Current environment (for creating child scope)
        
        Returns:
            UpdateSet from rule execution
            
        Raises:
            RuleEvaluationError: If rule not found or arity mismatch
            MaxRecursionError: If recursion depth exceeded
        """
        # Look up rule
        rule = self._rules.get(rule_name)
        if rule is None:
            raise RuleEvaluationError(f"Unknown rule: {rule_name}")
        
        # Check arity
        if len(args) != len(rule.parameters):
            raise RuleEvaluationError(
                f"Rule '{rule_name}' expects {len(rule.parameters)} arguments, "
                f"got {len(args)}"
            )
        
        # Check recursion depth
        self._recursion_depth += 1
        self._call_stack.append(rule_name)
        
        if self._recursion_depth > self._config.max_recursion_depth:
            raise MaxRecursionError(
                self._recursion_depth, 
                self._config.max_recursion_depth,
                rule_name
            )
        
        try:
            logger.debug(f"Invoking rule: {rule_name}({args}) [depth={self._recursion_depth}]")
            
            # Create new environment with parameters bound
            rule_env = env.child()
            for param, value in zip(rule.parameters, args):
                rule_env.bind(param, value)
            
            # Evaluate rule body
            if rule.body is None:
                logger.debug(f"Rule {rule_name} has no body (built-in)")
                return UpdateSet()
            
            return self.eval(rule.body, rule_env)
            
        finally:
            self._recursion_depth -= 1
            self._call_stack.pop()
    
    def get_call_stack(self) -> List[str]:
        """Get current call stack (for debugging)."""
        return self._call_stack.copy()
    
    # =========================================================================
    # Statement Evaluators
    # =========================================================================
    
    def _eval_skip(self, stmt: SkipStmt, env: Environment) -> UpdateSet:
        """
        Evaluate skip statement.
        
        Returns empty UpdateSet.
        """
        logger.debug("Evaluated skip")
        return UpdateSet()
    
    def _eval_update(self, stmt: UpdateStmt, env: Environment) -> UpdateSet:
        """
        Evaluate update statement: location := value
        
        Evaluates location arguments and value, creates Update.
        """
        # Evaluate location arguments
        loc_args = tuple(
            self._term_eval.eval(arg, env) 
            for arg in stmt.location.arguments
        )
        location = Location(stmt.location.func_name, loc_args)
        
        # Evaluate value
        value = self._term_eval.eval(stmt.value, env)
        
        logger.debug(f"Update: {location} := {value!r}")
        
        updates = UpdateSet()
        updates.add_update(location, value)
        return updates
    
    def _eval_seq(self, stmt: SeqStmt, env: Environment) -> UpdateSet:
        """
        Evaluate sequence of statements.
        
        Sequential semantics:
        - Each statement's updates are applied immediately
        - Next statement sees effects of previous statements
        
        Returns cumulative UpdateSet (for inspection/logging).
        Note: In sequential mode, later updates to same location override earlier ones.
        """
        updates = UpdateSet()
        
        for i, sub_stmt in enumerate(stmt.statements):
            logger.debug(f"SeqStmt: evaluating statement {i+1}/{len(stmt.statements)}")
            
            # Evaluate sub-statement
            sub_updates = self.eval(sub_stmt, env)
            
            # Apply to state immediately (sequential semantics)
            sub_updates.apply_to(self._state)
            
            # Track cumulative updates - in sequential mode, later values override
            for update in sub_updates:
                # Directly set in internal dict to allow override
                updates._updates[update.location] = update.value
        
        return updates
    
    def _eval_if(self, stmt: IfStmt, env: Environment) -> UpdateSet:
        """
        Evaluate conditional statement.
        
        Evaluates conditions in order until one is true.
        Only the chosen branch is executed.
        """
        # Check main condition
        cond_value = self._term_eval.eval(stmt.condition, env)
        if cond_value:
            logger.debug(f"IfStmt: main condition true")
            return self.eval(stmt.then_body, env)
        
        # Check elseif branches
        for i, (cond, body) in enumerate(stmt.elseif_branches):
            cond_value = self._term_eval.eval(cond, env)
            if cond_value:
                logger.debug(f"IfStmt: elseif branch {i+1} true")
                return self.eval(body, env)
        
        # Else branch
        if stmt.else_body is not None:
            logger.debug(f"IfStmt: else branch")
            return self.eval(stmt.else_body, env)
        
        logger.debug(f"IfStmt: no branch taken")
        return UpdateSet()
    
    def _eval_while(self, stmt: WhileStmt, env: Environment) -> UpdateSet:
        """
        Evaluate while loop.
        
        All iterations execute in ONE ASM step.
        Sequential semantics: condition re-evaluated on updated state.
        """
        updates = UpdateSet()
        iterations = 0
        
        while True:
            # Check condition
            cond_value = self._term_eval.eval(stmt.condition, env)
            if not cond_value:
                break
            
            iterations += 1
            if iterations > self._config.max_while_iterations:
                raise InfiniteLoopError(iterations, self._config.max_while_iterations)
            
            # Evaluate body
            body_updates = self.eval(stmt.body, env)
            
            # Apply immediately (sequential semantics)
            body_updates.apply_to(self._state)
            
            # Merge into cumulative (handle overrides)
            for update in body_updates:
                # In sequential while, later iterations can override
                # We track the final value for each location
                updates._updates[update.location] = update.value
        
        logger.debug(f"WhileStmt: completed after {iterations} iterations")
        return updates
    
    def _eval_forall(self, stmt: ForallStmt, env: Environment) -> UpdateSet:
        """
        Evaluate forall iteration.
        
        Parallel semantics:
        - All iterations see ORIGINAL state
        - Updates are collected and merged at end
        - Conflicts (same location, different values) raise error
        
        If guard is specified, only items where guard evaluates to true are processed.
        """
        # Evaluate collection
        collection = self._term_eval.eval(stmt.collection, env)
        
        if not isinstance(collection, (list, tuple)):
            raise RuleEvaluationError(
                f"Forall collection must be list or tuple, got {type(collection).__name__}"
            )
        
        if len(collection) == 0:
            logger.debug("ForallStmt: empty collection")
            return UpdateSet()
        
        updates = UpdateSet()
        processed_count = 0
        
        for i, item in enumerate(collection):
            # Create child environment with loop variable
            iter_env = env.child()
            iter_env.bind(stmt.var_name, item)
            
            # Check guard if present
            if stmt.guard is not None:
                guard_value = self._term_eval.eval(stmt.guard, iter_env)
                if not guard_value:
                    continue  # Skip this item
            
            processed_count += 1
            
            # Evaluate body (does NOT apply to state yet)
            body_updates = self.eval(stmt.body, iter_env)
            
            # Merge updates (conflict detection applies)
            try:
                updates.merge(body_updates)
            except UpdateConflictError as e:
                raise RuleEvaluationError(
                    f"Forall iteration {i+1}: conflicting updates to {e.location}"
                ) from e
        
        logger.debug(f"ForallStmt: processed {processed_count}/{len(collection)} items")
        return updates
    
    def _eval_choose(self, stmt: ChooseStmt, env: Environment) -> UpdateSet:
        """
        Evaluate choose statement (nondeterministic selection).
        
        Selects ONE element from collection (first matching if guard present).
        If no elements match, body is not executed.
        """
        # Evaluate collection
        collection = self._term_eval.eval(stmt.collection, env)
        
        if not isinstance(collection, (list, tuple)):
            raise RuleEvaluationError(
                f"Choose collection must be list or tuple, got {type(collection).__name__}"
            )
        
        if len(collection) == 0:
            logger.debug("ChooseStmt: empty collection")
            return UpdateSet()
        
        # Find first matching element
        for item in collection:
            # Create child environment with loop variable
            iter_env = env.child()
            iter_env.bind(stmt.var_name, item)
            
            # Check guard if present
            if stmt.guard is not None:
                guard_value = self._term_eval.eval(stmt.guard, iter_env)
                if not guard_value:
                    continue  # Skip this item
            
            # Found a matching element - evaluate body once
            logger.debug(f"ChooseStmt: selected {item!r}")
            return self.eval(stmt.body, iter_env)
        
        # No matching element found
        logger.debug("ChooseStmt: no matching element")
        return UpdateSet()
    
    def _eval_par(self, stmt: ParStmt, env: Environment) -> UpdateSet:
        """
        Evaluate parallel block.
        
        All statements in body see ORIGINAL state.
        Updates are collected and merged at end.
        Conflicts raise error.
        
        Note: If body is SeqStmt, we must evaluate each statement
        on the original state, not sequentially.
        """
        if isinstance(stmt.body, SeqStmt):
            # Parallel execution of statements
            updates = UpdateSet()
            
            for sub_stmt in stmt.body.statements:
                # Each statement sees original state
                sub_updates = self._eval_single_parallel(sub_stmt, env)
                
                try:
                    updates.merge(sub_updates)
                except UpdateConflictError as e:
                    raise RuleEvaluationError(
                        f"ParStmt: conflicting updates to {e.location}"
                    ) from e
            
            logger.debug(f"ParStmt: {len(stmt.body.statements)} parallel statements")
            return updates
        else:
            # Single statement - just evaluate normally
            return self.eval(stmt.body, env)
    
    def _eval_single_parallel(self, stmt: Stmt, env: Environment) -> UpdateSet:
        """
        Evaluate a single statement in parallel context.
        
        Does NOT apply updates to state (parallel semantics).
        """
        # For most statements, we can just evaluate normally
        # But we need to NOT apply SeqStmt/WhileStmt updates mid-execution
        if isinstance(stmt, (SkipStmt, UpdateStmt, IfStmt, ForallStmt, 
                            LetStmt, RuleCallStmt, PrintStmt, ChooseStmt,
                            LibCallStmt, RndCallStmt)):
            return self.eval(stmt, env)
        elif isinstance(stmt, SeqStmt):
            # Nested sequence in parallel - still parallel semantics
            updates = UpdateSet()
            for sub_stmt in stmt.statements:
                sub_updates = self._eval_single_parallel(sub_stmt, env)
                try:
                    updates.merge(sub_updates)
                except UpdateConflictError as e:
                    raise RuleEvaluationError(
                        f"ParStmt nested sequence: conflicting updates to {e.location}"
                    ) from e
            return updates
        elif isinstance(stmt, WhileStmt):
            # While in parallel context is problematic - use sequential semantics
            logger.warning("WhileStmt inside ParStmt uses sequential semantics")
            return self._eval_while(stmt, env)
        elif isinstance(stmt, ParStmt):
            # Nested parallel - just flatten
            return self._eval_par(stmt, env)
        else:
            return self.eval(stmt, env)
    
    def _eval_lib_call_stmt(self, stmt: LibCallStmt, env: Environment) -> UpdateSet:
        """
        Evaluate library function call as statement.
        
        Calls the function for its side effects (e.g., lib.add, lib.remove).
        Return value is discarded.
        """
        if self._term_eval._stdlib is None:
            raise RuleEvaluationError("Standard library not set")
        
        func_name = stmt.func_name
        
        # Check if function exists
        if not hasattr(self._term_eval._stdlib, func_name):
            raise RuleEvaluationError(f"Unknown library function: lib.{func_name}")
        
        # Evaluate arguments
        args = [self._term_eval.eval(arg, env) for arg in stmt.arguments]
        
        # Call function
        func = getattr(self._term_eval._stdlib, func_name)
        try:
            func(*args)
            logger.debug(f"LibCallStmt: lib.{func_name}({args})")
        except Exception as e:
            raise RuleEvaluationError(
                f"Error calling lib.{func_name}: {e}"
            ) from e
        
        return UpdateSet()
    
    def _eval_rnd_call_stmt(self, stmt: RndCallStmt, env: Environment) -> UpdateSet:
        """
        Evaluate random function call as statement.
        
        Calls the function for its side effects (e.g., rnd.seed).
        Return value is discarded.
        """
        if self._term_eval._rng is None:
            raise RuleEvaluationError("Random generator not set")
        
        func_name = stmt.func_name
        stream = stmt.stream
        
        # Evaluate arguments
        args = [self._term_eval.eval(arg, env) for arg in stmt.arguments]
        
        # Get the appropriate stream
        if stream:
            rng = self._term_eval._rng.stream(stream)
        else:
            rng = self._term_eval._rng
        
        # Check if function exists
        if not hasattr(rng, func_name):
            raise RuleEvaluationError(f"Unknown random function: rnd.{func_name}")
        
        # Call function
        func = getattr(rng, func_name)
        try:
            func(*args)
            if stream:
                logger.debug(f"RndCallStmt: rnd.{stream}.{func_name}({args})")
            else:
                logger.debug(f"RndCallStmt: rnd.{func_name}({args})")
        except Exception as e:
            raise RuleEvaluationError(
                f"Error calling rnd.{func_name}: {e}"
            ) from e
        
        return UpdateSet()
    
    def _eval_let(self, stmt: LetStmt, env: Environment) -> UpdateSet:
        """
        Evaluate let binding.
        
        Binds variable in current environment.
        Scope extends to end of enclosing block.
        Does NOT produce updates.
        """
        value = self._term_eval.eval(stmt.value, env)
        env.bind(stmt.var_name, value)
        logger.debug(f"LetStmt: {stmt.var_name} = {value!r}")
        return UpdateSet()
    
    def _eval_rule_call(self, stmt: RuleCallStmt, env: Environment) -> UpdateSet:
        """
        Evaluate rule call.
        
        Supports static and dynamic dispatch:
        - Static: rule_name is VariableTerm or LiteralTerm
        - Dynamic: rule_name is LocationTerm (e.g., event_rule(e))
        """
        # Determine rule name
        if isinstance(stmt.rule_name, VariableTerm):
            # Could be let-bound variable containing rule name
            if env.contains(stmt.rule_name.name):
                rule_name = env.lookup(stmt.rule_name.name)
            else:
                # Treat as literal rule name
                rule_name = stmt.rule_name.name
        elif isinstance(stmt.rule_name, LiteralTerm):
            rule_name = stmt.rule_name.value
        elif isinstance(stmt.rule_name, LocationTerm):
            # Dynamic dispatch: event_rule(e) reads from state
            rule_name = self._term_eval.eval(stmt.rule_name, env)
        else:
            # General case: evaluate as term
            rule_name = self._term_eval.eval(stmt.rule_name, env)
        
        if not isinstance(rule_name, str):
            raise RuleEvaluationError(
                f"Rule name must be string, got {type(rule_name).__name__}: {rule_name!r}"
            )
        
        # Check rule exists (at call time, not assignment time was previous decision,
        # but we check here anyway for better error messages)
        if not self._rules.exists(rule_name):
            raise RuleEvaluationError(f"Unknown rule: {rule_name}")
        
        # Evaluate arguments
        args = [self._term_eval.eval(arg, env) for arg in stmt.arguments]
        
        logger.debug(f"RuleCallStmt: {rule_name}({args})")
        
        # Invoke rule
        return self.invoke_rule(rule_name, args, env)
    
    def _eval_print(self, stmt: PrintStmt, env: Environment) -> UpdateSet:
        """
        Evaluate print statement.
        
        Outputs value to console or configured callback.
        Does NOT produce updates.
        """
        value = self._term_eval.eval(stmt.expression, env)
        
        if self._config.print_callback:
            self._config.print_callback(value)
        else:
            print(f"[SimASM] {value}")
        
        logger.debug(f"PrintStmt: {value!r}")
        return UpdateSet()
