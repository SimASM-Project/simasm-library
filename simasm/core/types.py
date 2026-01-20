"""
core/types.py

Domain and type hierarchy for SimASM.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Set, List

from simasm.log.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Domain:
    """
    Represents a domain declaration.
    
    Examples:
        Domain("Object")                    # domain Object
        Domain("Generator", "Object")       # domain Generator <: Object
        Domain("ArriveEvent", "Event")      # domain ArriveEvent <: Event
        Domain("PositiveReal", "Real")      # domain PositiveReal <: Real (extending built-in)
    """
    name: str
    parent: Optional[str] = None  # None means no parent (top-level domain)


# Built-in type names (pre-registered, can be extended)
BUILTIN_TYPES = frozenset({
    "Nat",      # Natural numbers (0, 1, 2, ...)
    "Int",      # Integers (..., -1, 0, 1, ...)
    "Real",     # Real numbers (floating point)
    "Bool",     # Boolean (true, false)
    "String",   # Text strings
    "List",     # List type (generic, but not enforced in v1.0)
    "Any",      # Any type (for dynamic typing)
    "Rule",     # Rule reference (stored as string, invoked via lib.apply_rule)
})


class TypeRegistry:
    """
    Manages all declared domains and their hierarchy.
    
    Built-in types (Nat, Real, Bool, etc.) are pre-registered.
    User domains can extend other domains including built-in types.
    
    Usage:
        registry = TypeRegistry()
        registry.register(Domain("Object"))
        registry.register(Domain("Load", "Object"))
        
        registry.is_subtype("Load", "Object")  # True
        registry.is_subtype("Object", "Load")  # False
        registry.is_subtype("Load", "Load")    # True (reflexive)
    """
    
    def __init__(self):
        self._domains: Dict[str, Domain] = {}
        self._register_builtins()
        logger.debug("TypeRegistry initialized with built-in types")
    
    def _register_builtins(self) -> None:
        """Pre-register built-in types."""
        for name in BUILTIN_TYPES:
            self._domains[name] = Domain(name, None)
        logger.debug(f"Registered {len(BUILTIN_TYPES)} built-in types")
    
    def register(self, domain: Domain) -> None:
        """
        Register a domain declaration.
        
        Raises:
            ValueError: If domain already registered
            ValueError: If parent specified but not registered
        """
        # Check duplicate
        if domain.name in self._domains:
            logger.error(f"Domain already registered: {domain.name}")
            raise ValueError(f"Domain already registered: {domain.name}")
        
        # Check parent exists
        if domain.parent is not None and domain.parent not in self._domains:
            logger.error(f"Parent domain not registered: {domain.parent}")
            raise ValueError(f"Parent domain not registered: {domain.parent}")
        
        self._domains[domain.name] = domain
        logger.info(f"Registered domain: {domain.name}" + 
                   (f" <: {domain.parent}" if domain.parent else ""))
    
    def get(self, name: str) -> Optional[Domain]:
        """Get domain by name, or None if not found."""
        return self._domains.get(name)
    
    def exists(self, name: str) -> bool:
        """Check if domain is registered."""
        return name in self._domains
    
    def is_builtin(self, name: str) -> bool:
        """Check if name is a built-in type."""
        return name in BUILTIN_TYPES
    
    def is_subtype(self, child: str, parent: str) -> bool:
        """
        Check if child domain is subtype of parent domain.
        
        Rules:
        - Reflexive: A <: A (any domain is subtype of itself)
        - Transitive: if A <: B and B <: C, then A <: C
        
        Returns False if either domain not registered.
        """
        # Check both exist
        if child not in self._domains or parent not in self._domains:
            return False
        
        # Reflexive case
        if child == parent:
            return True
        
        # Walk up the hierarchy
        current = child
        while current is not None:
            domain = self._domains.get(current)
            if domain is None:
                return False
            if domain.parent == parent:
                return True
            current = domain.parent
        
        return False
    
    def get_ancestors(self, name: str) -> List[str]:
        """
        Return list of ancestors from immediate parent to root.
        
        Returns empty list if domain not found or has no parent.
        
        Example:
            # Given: ArriveEvent <: Event <: Object
            get_ancestors("ArriveEvent")  # ["Event", "Object"]
            get_ancestors("Object")        # []
        """
        ancestors = []
        domain = self._domains.get(name)
        
        while domain is not None and domain.parent is not None:
            ancestors.append(domain.parent)
            domain = self._domains.get(domain.parent)
        
        return ancestors
    
    def all_domains(self) -> Set[str]:
        """Return all registered domain names (including built-ins)."""
        return set(self._domains.keys())
    
    def user_domains(self) -> Set[str]:
        """Return only user-defined domain names (excluding built-ins)."""
        return set(self._domains.keys()) - BUILTIN_TYPES
