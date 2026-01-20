"""
parser/loader.py

Loads a parsed Program AST into executable runtime objects.

Provides:
- ProgramLoader: Converts Program to runtime (TypeRegistry, ASMState, RuleRegistry, etc.)
- load_program: Convenience function
- LoadError: Exception for loading failures
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from simasm.core.types import TypeRegistry, Domain
from simasm.core.state import ASMState, Location
from simasm.core.terms import (
    Environment, TermEvaluator,
    LiteralTerm, VariableTerm, LocationTerm,
)
from simasm.core.rules import (
    RuleDefinition, RuleRegistry, RuleEvaluator, RuleEvaluatorConfig,
)
from simasm.runtime.stdlib import StandardLibrary
from simasm.runtime.random import RandomStream, RandomRegistry
import zlib


def _deterministic_hash(name: str) -> int:
    """
    Compute a deterministic hash for a string.

    Unlike Python's built-in hash(), this returns the same value
    across different Python invocations (PYTHONHASHSEED doesn't affect it).
    """
    return zlib.crc32(name.encode('utf-8')) & 0xffffffff


class SimASMRandom(RandomStream):
    """
    Combined random interface for SimASM programs.
    
    Extends RandomStream to support both:
    - Direct calls: rnd.uniform(0, 1) - uses default stream
    - Named streams: rnd.arrivals.exponential(10) - uses named stream
    
    Usage:
        rng = SimASMRandom(seed=42)
        
        # Default stream
        val = rng.uniform(0, 100)
        
        # Named stream (created on demand)
        arrival = rng.stream("arrivals").exponential(10)
    """
    
    def __init__(self, seed: Optional[int] = None):
        """
        Create SimASMRandom with default stream.
        
        Args:
            seed: Seed for default stream and base for named streams
        """
        super().__init__(seed)
        self._registry = RandomRegistry()
        self._base_seed = seed if seed is not None else 42
        self._stream_counter = 0
    
    def stream(self, name: str) -> RandomStream:
        """
        Get or create a named stream.
        
        Args:
            name: Stream name
            
        Returns:
            RandomStream for that name
        """
        if not self._registry.exists(name):
            # Create stream with deterministic seed derived from base
            # Use _deterministic_hash instead of hash() for reproducibility
            # across different Python invocations (PYTHONHASHSEED)
            derived_seed = self._base_seed + _deterministic_hash(name) % 10000
            self._registry.create(name, seed=derived_seed)
        
        return self._registry.get(name)
    
    def reset_all(self) -> None:
        """Reset default stream and all named streams."""
        self.reset()
        self._registry.reset_all()

from simasm.parser.ast import (
    Program, ImportDecl, DomainDecl, ConstDecl, VarDecl,
    StaticFuncDecl, DynamicFuncDecl, DerivedFuncDecl,
    RuleDecl, MainRuleDecl, InitBlock,
    SimpleType, ParamType, RndStreamType,
)


class LoadError(Exception):
    """Raised when loading a program fails."""
    pass


@dataclass
class LoadedProgram:
    """
    A fully loaded and ready-to-run SimASM program.
    
    Contains all runtime objects needed for execution.
    """
    # Core runtime
    types: TypeRegistry
    state: ASMState
    rules: RuleRegistry
    
    # Evaluators
    term_evaluator: TermEvaluator
    rule_evaluator: RuleEvaluator
    
    # Runtime support
    stdlib: StandardLibrary
    rng: SimASMRandom
    
    # Program metadata
    main_rule_name: Optional[str] = None
    imports: Dict[str, str] = None  # alias -> module
    
    def __post_init__(self):
        if self.imports is None:
            self.imports = {}


class ProgramLoader:
    """
    Loads a parsed Program AST into runtime objects.
    
    Usage:
        from simasm.parser import parse_string
        from simasm.parser.loader import ProgramLoader
        
        program = parse_string(source_code)
        loader = ProgramLoader()
        loaded = loader.load(program)
        
        # Now ready to run
        stepper = ASMStepper(
            state=loaded.state,
            rules=loaded.rules,
            term_evaluator=loaded.term_evaluator,
            main_rule=loaded.main_rule_name
        )
    """
    
    def __init__(self, seed: int = 42):
        """
        Create loader.
        
        Args:
            seed: Random seed for the loaded program
        """
        self._seed = seed
    
    def load(self, program: Program) -> LoadedProgram:
        """
        Load a Program AST into runtime objects.
        
        Args:
            program: Parsed Program AST
            
        Returns:
            LoadedProgram with all runtime objects
            
        Raises:
            LoadError: If loading fails
        """
        # 1. Create type registry and register domains
        types = self._load_types(program)
        
        # 2. Create ASM state
        state = ASMState(types)
        
        # 3. Process imports
        imports = self._load_imports(program)
        
        # 4. Create rule registry and load rules
        rules = self._load_rules(program, types)
        
        # 5. Create runtime support
        stdlib = StandardLibrary(state, rules)
        rng = SimASMRandom(seed=self._seed)
        
        # 6. Create term evaluator
        term_evaluator = TermEvaluator(state, types)
        term_evaluator.set_stdlib(stdlib)
        term_evaluator.set_rng(rng)
        
        # 6b. Set up derived functions
        derived_funcs = {}
        for decl in program.derived_funcs:
            derived_funcs[decl.name] = decl
        term_evaluator.set_derived_funcs(derived_funcs)

        # 6c. Set up stream variables (var name: rnd.distribution(args))
        stream_vars = {}
        for decl in program.variables:
            if isinstance(decl.type_expr, RndStreamType):
                stream_vars[decl.name] = decl.type_expr
        term_evaluator.set_stream_vars(stream_vars)
        
        # 7. Create rule evaluator
        rule_evaluator = RuleEvaluator(state, rules, term_evaluator)
        
        # 7b. Connect stdlib to rule evaluator (for lib.apply_rule)
        stdlib.set_evaluator(rule_evaluator)
        
        # 8. Initialize state with declarations
        self._initialize_state(program, state, term_evaluator)
        
        # 9. Run init block
        if program.init:
            self._run_init(program.init, rule_evaluator, Environment())
        
        # 10. Get main rule name
        main_rule_name = program.main_rule.name if program.main_rule else None
        
        return LoadedProgram(
            types=types,
            state=state,
            rules=rules,
            term_evaluator=term_evaluator,
            rule_evaluator=rule_evaluator,
            stdlib=stdlib,
            rng=rng,
            main_rule_name=main_rule_name,
            imports=imports,
        )
    
    def _load_types(self, program: Program) -> TypeRegistry:
        """Load domains into type registry."""
        types = TypeRegistry()
        
        for decl in program.domains:
            domain = Domain(name=decl.name, parent=decl.parent)
            try:
                types.register(domain)
            except ValueError as e:
                raise LoadError(f"Error registering domain {decl.name}: {e}") from e
        
        return types
    
    def _load_imports(self, program: Program) -> Dict[str, str]:
        """Process import declarations."""
        imports = {}
        
        for decl in program.imports:
            imports[decl.alias] = decl.module
            
            # Validate known modules
            if decl.module not in ("Random", "Stdlib"):
                raise LoadError(f"Unknown module: {decl.module}")
        
        return imports
    
    def _load_rules(self, program: Program, types: TypeRegistry) -> RuleRegistry:
        """Load rule declarations into registry."""
        rules = RuleRegistry()
        
        # Load regular rules
        for decl in program.rules:
            param_names = [p.name for p in decl.params]
            rule_def = RuleDefinition(
                name=decl.name,
                parameters=param_names,
                body=decl.body,
            )
            try:
                rules.register(rule_def)
            except ValueError as e:
                raise LoadError(f"Error registering rule {decl.name}: {e}") from e
        
        # Load main rule
        if program.main_rule:
            main_def = RuleDefinition(
                name=program.main_rule.name,
                parameters=[],
                body=program.main_rule.body,
            )
            try:
                rules.register(main_def)
            except ValueError as e:
                raise LoadError(f"Error registering main rule: {e}") from e
        
        return rules
    
    def _initialize_state(
        self,
        program: Program,
        state: ASMState,
        term_evaluator: TermEvaluator
    ) -> None:
        """
        Initialize state with const/var/function declarations.
        
        Note: We don't set initial values here - that's done in init block.
        We just ensure the locations exist in state (set to UNDEF by default).
        """
        # Constants - mark as locations (values set in init)
        for decl in program.constants:
            # Just touch the location so it exists
            loc = Location(decl.name, ())
            # State returns UNDEF for unknown locations, so no action needed
        
        # Variables - same as constants
        for decl in program.variables:
            loc = Location(decl.name, ())
            # State returns UNDEF for unknown locations
        
        # Static functions - these have fixed values, not set via state
        # (In full implementation, would store separately)
        
        # Dynamic functions - these are state locations
        # (No initialization needed - accessed via state.get/set)
        
        # Derived functions - computed on demand
        # Store the expression for later evaluation
        self._derived_funcs: Dict[str, DerivedFuncDecl] = {}
        for decl in program.derived_funcs:
            self._derived_funcs[decl.name] = decl
    
    def _run_init(
        self,
        init: InitBlock,
        rule_evaluator: RuleEvaluator,
        env: Environment
    ) -> None:
        """Execute the init block."""
        try:
            updates = rule_evaluator.eval(init.body, env)
            updates.apply_to(rule_evaluator.state)
        except Exception as e:
            raise LoadError(f"Error in init block: {e}") from e


# ============================================================================
# Convenience Functions
# ============================================================================

def load_program(program: Program, seed: int = 42) -> LoadedProgram:
    """
    Load a parsed Program into runtime objects.
    
    Convenience function using default ProgramLoader.
    
    Args:
        program: Parsed Program AST
        seed: Random seed
        
    Returns:
        LoadedProgram ready for execution
        
    Example:
        from simasm.parser import parse_string
        from simasm.parser.loader import load_program
        
        program = parse_string(source)
        loaded = load_program(program)
    """
    loader = ProgramLoader(seed=seed)
    return loader.load(program)


def load_string(source: str, seed: int = 42) -> LoadedProgram:
    """
    Parse and load SimASM source code.
    
    Combines parsing and loading in one call.
    
    Args:
        source: SimASM source code
        seed: Random seed
        
    Returns:
        LoadedProgram ready for execution
        
    Example:
        from simasm.parser.loader import load_string
        
        loaded = load_string('''
            domain Load
            var counter: Int
            init: counter := 0 endinit
        ''')
    """
    from simasm.parser import parse_string
    program = parse_string(source)
    return load_program(program, seed=seed)


def load_file(path: str, seed: int = 42) -> LoadedProgram:
    """
    Parse and load SimASM file.
    
    Args:
        path: Path to .simasm file
        seed: Random seed
        
    Returns:
        LoadedProgram ready for execution
    """
    from simasm.parser import parse_file
    program = parse_file(path)
    return load_program(program, seed=seed)
