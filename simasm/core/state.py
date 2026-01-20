"""
core/state.py

ASM state representation for SimASM.

This module provides:
- UNDEF: Singleton sentinel for undefined locations
- ASMObject: Runtime objects created by 'new Domain'
- Location: State location (function_name, arguments)
- ASMState: Complete state mapping (Section 3)
"""

from typing import Any, Dict, Tuple

from simasm.log.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# UNDEF - Undefined value sentinel
# ============================================================================

class Undefined:
    """
    Singleton sentinel value for undefined locations.
    
    In ASM, accessing an unset function location returns 'undef'.
    This class provides a unique sentinel that can be checked with 'is' or '=='.
    
    Usage:
        if value is UNDEF:
            # Location was not set
        
        if value == UNDEF:
            # Also works
        
        if value is not UNDEF:
            # Location has a value
    
    Properties:
        - Singleton: Only one instance exists
        - Falsy: bool(UNDEF) returns False
        - Repr: str(UNDEF) returns "undef"
        - Equality: UNDEF == UNDEF is True, UNDEF == anything_else is False
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            logger.debug("Created UNDEF singleton")
        return cls._instance
    
    def __repr__(self) -> str:
        return "undef"
    
    def __str__(self) -> str:
        return "undef"
    
    def __bool__(self) -> bool:
        return False
    
    def __eq__(self, other) -> bool:
        """UNDEF equals only itself."""
        return other is self
    
    def __ne__(self, other) -> bool:
        return other is not self
    
    def __hash__(self) -> int:
        return hash("UNDEF_SENTINEL")


# The singleton instance
UNDEF = Undefined()


# ============================================================================
# ASMObject - Runtime objects
# ============================================================================

class ASMObject:
    """
    Runtime object created by 'new Domain'.
    
    Each object has:
    - domain: The domain it belongs to (e.g., "Load", "Event")
    - _internal_id: Auto-assigned, domain-specific counter
    
    Properties:
    - Hashable: Can be used as dictionary keys
    - Comparable: Two objects equal iff same domain and internal_id
    - Reproducible: Same execution order produces same IDs
    
    Usage:
        load1 = ASMObject("Load")   # Load#1
        load2 = ASMObject("Load")   # Load#2
        event1 = ASMObject("Event") # Event#1
        
        # Can be dict keys
        data = {load1: "first", load2: "second"}
        
        # Reset for new simulation
        ASMObject.reset_counters()
    
    Display:
        str(load1) returns "Load#1"
    
    Comparison:
        - ASMObject can only be compared with ASMObject
        - Comparing with other types raises TypeError
    """
    
    _counters: Dict[str, int] = {}  # Class-level, per-domain counters
    
    def __init__(self, domain: str):
        """
        Create a new object of the given domain.
        
        Args:
            domain: The domain name (e.g., "Load", "Event", "Server")
        """
        self.domain = domain
        self._internal_id = self._next_id(domain)
        logger.debug(f"Created {self}")
    
    @classmethod
    def _next_id(cls, domain: str) -> int:
        """Get next ID for domain, incrementing counter."""
        if domain not in cls._counters:
            cls._counters[domain] = 0
        cls._counters[domain] += 1
        return cls._counters[domain]
    
    @classmethod
    def reset_counters(cls) -> None:
        """
        Reset all counters (for new simulation run).
        
        Call this before starting a new simulation to ensure
        reproducible object IDs.
        """
        cls._counters.clear()
        logger.debug("Reset all ASMObject counters")
    
    @classmethod
    def get_counter(cls, domain: str) -> int:
        """Get current counter value for a domain (for testing/debugging)."""
        return cls._counters.get(domain, 0)
    
    @property
    def internal_id(self) -> int:
        """Read-only access to internal ID."""
        return self._internal_id
    
    def __eq__(self, other) -> bool:
        """
        Two objects are equal iff same domain and internal_id.
        
        Raises:
            TypeError: If comparing with non-ASMObject
        """
        if not isinstance(other, ASMObject):
            raise TypeError(
                f"Cannot compare ASMObject with {type(other).__name__}. "
                f"ASMObject can only be compared with ASMObject."
            )
        return self.domain == other.domain and self._internal_id == other._internal_id
    
    def __ne__(self, other) -> bool:
        """Not equal."""
        return not self.__eq__(other)
    
    def __hash__(self) -> int:
        """Hash based on domain and internal_id."""
        return hash((self.domain, self._internal_id))
    
    def __repr__(self) -> str:
        """Returns 'Domain#id' format."""
        return f"{self.domain}#{self._internal_id}"
    
    def __str__(self) -> str:
        return self.__repr__()


# ============================================================================
# Location - State location
# ============================================================================

class Location:
    """
    A location in ASM state: (function_name, arguments).
    
    Locations identify where values are stored in state.
    They consist of a function name and a tuple of arguments.
    
    Examples:
        # 0-ary (variable): x
        Location("x")
        Location("x", ())
        
        # 1-ary: queues(queue)
        Location("queues", (queue_obj,))
        Location("queues", queue_obj)  # Auto-wrapped to tuple
        
        # 2-ary: distance(a, b)  
        Location("distance", (obj_a, obj_b))
        
        # With ASMObject arguments
        load = ASMObject("Load")
        Location("status", load)  # Auto-wrapped to (load,)
    
    Properties:
        - Frozen: Immutable after creation
        - Hashable: Can be used as dictionary keys
        - Auto-wrap: Single non-tuple arg is wrapped in tuple
    """
    
    __slots__ = ('_func_name', '_args')
    
    def __init__(self, func_name: str, args: Any = ()):
        """
        Create a new Location with auto-wrapping of args.
        
        Args:
            func_name: The function/variable name
            args: Arguments tuple, or single arg (will be wrapped)
        """
        # Normalize args to tuple
        if args is None:
            normalized_args = ()
        elif isinstance(args, tuple):
            normalized_args = args
        else:
            normalized_args = (args,)
        
        # Use object.__setattr__ to set on frozen-like object
        object.__setattr__(self, '_func_name', func_name)
        object.__setattr__(self, '_args', normalized_args)
    
    @property
    def func_name(self) -> str:
        """The function/variable name."""
        return self._func_name
    
    @property
    def args(self) -> Tuple[Any, ...]:
        """The arguments tuple."""
        return self._args
    
    @property
    def arity(self) -> int:
        """Number of arguments."""
        return len(self._args)
    
    @property
    def is_variable(self) -> bool:
        """True if 0-ary (a simple variable)."""
        return len(self._args) == 0
    
    def __setattr__(self, name, value):
        """Prevent attribute modification (frozen behavior)."""
        raise AttributeError(f"Cannot modify immutable Location: {name}")
    
    def __delattr__(self, name):
        """Prevent attribute deletion (frozen behavior)."""
        raise AttributeError(f"Cannot delete from immutable Location: {name}")
    
    def __eq__(self, other) -> bool:
        """Locations are equal if func_name and args match."""
        if not isinstance(other, Location):
            return NotImplemented
        return self._func_name == other._func_name and self._args == other._args
    
    def __ne__(self, other) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result
    
    def __hash__(self) -> int:
        """Hash based on func_name and args."""
        return hash((self._func_name, self._args))
    
    def __repr__(self) -> str:
        if self.is_variable:
            return f"Location({self._func_name!r})"
        elif len(self._args) == 1:
            return f"Location({self._func_name!r}, ({self._args[0]!r},))"
        else:
            args_str = ", ".join(repr(a) for a in self._args)
            return f"Location({self._func_name!r}, ({args_str}))"
    
    def __str__(self) -> str:
        """Human-readable format: 'func_name' or 'func_name(arg1, arg2)'."""
        if self.is_variable:
            return self._func_name
        else:
            args_str = ", ".join(str(a) for a in self._args)
            return f"{self._func_name}({args_str})"


# ============================================================================
# ASMState - Complete ASM state
# ============================================================================

class ASMState:
    """
    The complete state of an ASM.
    
    State is a mapping from Locations to Values.
    Internally organized for efficient access:
    - _variables: {name: value} for 0-ary functions
    - _functions: {func_name: {args_tuple: value}} for n-ary functions
    
    Properties:
    - Undefined locations return UNDEF
    - Setting a location to UNDEF stores UNDEF (does not delete)
    - Supports deep copy for state snapshots
    - Integrates with TypeRegistry
    
    Usage:
        state = ASMState()
        
        # Variables (0-ary)
        state.set_var("x", 10)
        state.get_var("x")      # 10
        state.get_var("y")      # UNDEF
        
        # Functions (n-ary)
        load = ASMObject("Load")
        state.set_func("status", (load,), "waiting")
        state.get_func("status", (load,))  # "waiting"
        
        # Generic Location access
        loc = Location("status", load)
        state.get(loc)          # "waiting"
        state.set(loc, "done")
        
        # Copy for snapshots
        state2 = state.copy()
    """
    
    def __init__(self, types: 'TypeRegistry' = None):
        """
        Create a new ASM state.
        
        Args:
            types: Optional TypeRegistry. Creates new one if not provided.
        """
        # Import here to avoid circular import
        from .types import TypeRegistry
        
        self._variables: Dict[str, Any] = {}
        self._functions: Dict[str, Dict[Tuple, Any]] = {}
        self.types: TypeRegistry = types if types is not None else TypeRegistry()
        logger.debug("Created new ASMState")
    
    # ========================================================================
    # Generic Location-based access
    # ========================================================================
    
    def get(self, location: Location) -> Any:
        """
        Get value at location.
        
        Args:
            location: The location to look up
            
        Returns:
            The value at location, or UNDEF if not set
        """
        if location.is_variable:
            return self.get_var(location.func_name)
        else:
            return self.get_func(location.func_name, location.args)
    
    def set(self, location: Location, value: Any) -> None:
        """
        Set value at location.
        
        Args:
            location: The location to set
            value: The value to store (can be UNDEF)
        """
        if location.is_variable:
            self.set_var(location.func_name, value)
        else:
            self.set_func(location.func_name, location.args, value)
    
    # ========================================================================
    # Convenience: 0-ary (variables)
    # ========================================================================
    
    def get_var(self, name: str) -> Any:
        """
        Get variable (0-ary function) value.
        
        Args:
            name: Variable name
            
        Returns:
            The value, or UNDEF if not set
        """
        return self._variables.get(name, UNDEF)
    
    def set_var(self, name: str, value: Any) -> None:
        """
        Set variable (0-ary function) value.
        
        Args:
            name: Variable name
            value: Value to store (can be UNDEF)
        """
        self._variables[name] = value
        logger.debug(f"Set variable {name} := {value}")
    
    # ========================================================================
    # Convenience: n-ary (functions)
    # ========================================================================
    
    def get_func(self, func_name: str, args: Tuple) -> Any:
        """
        Get function value at given arguments.
        
        Args:
            func_name: Function name
            args: Arguments tuple
            
        Returns:
            The value, or UNDEF if not set
        """
        if func_name not in self._functions:
            return UNDEF
        return self._functions[func_name].get(args, UNDEF)
    
    def set_func(self, func_name: str, args: Tuple, value: Any) -> None:
        """
        Set function value at given arguments.
        
        Args:
            func_name: Function name
            args: Arguments tuple
            value: Value to store (can be UNDEF)
        """
        if func_name not in self._functions:
            self._functions[func_name] = {}
        self._functions[func_name][args] = value
        logger.debug(f"Set {func_name}{args} := {value}")
    
    # ========================================================================
    # State operations
    # ========================================================================
    
    def copy(self) -> 'ASMState':
        """
        Create a deep copy of this state.
        
        Returns:
            New ASMState with copied data (shares TypeRegistry reference)
        """
        import copy
        new_state = ASMState(self.types)  # Share types reference
        new_state._variables = copy.deepcopy(self._variables)
        new_state._functions = copy.deepcopy(self._functions)
        logger.debug("Created state copy")
        return new_state
    
    def locations(self) -> set:
        """
        Return all defined locations.
        
        Returns:
            Set of all Locations that have been set (including those set to UNDEF)
        """
        locs = set()
        
        # Add variables
        for name in self._variables:
            locs.add(Location(name))
        
        # Add functions
        for func_name, args_dict in self._functions.items():
            for args in args_dict:
                locs.add(Location(func_name, args))
        
        return locs
    
    def clear(self) -> None:
        """
        Clear all state (variables and functions).
        
        TypeRegistry is preserved.
        """
        self._variables.clear()
        self._functions.clear()
        logger.debug("Cleared ASMState")
    
    def __contains__(self, location: Location) -> bool:
        """
        Check if location has been set (even if set to UNDEF).
        
        Args:
            location: Location to check
            
        Returns:
            True if location was ever set, False otherwise
        """
        if location.is_variable:
            return location.func_name in self._variables
        else:
            if location.func_name not in self._functions:
                return False
            return location.args in self._functions[location.func_name]
    
    def __len__(self) -> int:
        """
        Return number of defined locations.
        """
        count = len(self._variables)
        for args_dict in self._functions.values():
            count += len(args_dict)
        return count
    
    def __repr__(self) -> str:
        return f"ASMState(variables={len(self._variables)}, functions={len(self._functions)})"
    
    def __str__(self) -> str:
        lines = ["ASMState:"]
        
        # Variables
        if self._variables:
            lines.append("  Variables:")
            for name, value in sorted(self._variables.items()):
                lines.append(f"    {name} = {value}")
        
        # Functions
        if self._functions:
            lines.append("  Functions:")
            for func_name in sorted(self._functions.keys()):
                for args, value in self._functions[func_name].items():
                    args_str = ", ".join(str(a) for a in args)
                    lines.append(f"    {func_name}({args_str}) = {value}")
        
        if len(lines) == 1:
            return "ASMState: (empty)"
        
        return "\n".join(lines)
