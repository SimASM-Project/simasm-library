"""
core/update.py

Update representation and conflict detection for SimASM.

This module provides:
- Update: A single pending state change (location := value)
- UpdateConflictError: Exception for conflicting updates
- UpdateSet: Collection of updates with conflict detection
"""

from dataclasses import dataclass
from typing import Any, Dict, Iterator

from simasm.log.logger import get_logger
from .state import Location, ASMState, UNDEF

logger = get_logger(__name__)


# ============================================================================
# Update - Single pending update
# ============================================================================

@dataclass(frozen=True)
class Update:
    """
    A single pending update: location := value.
    
    Immutable and hashable. Can be collected in sets.
    
    Usage:
        update = Update(Location("x"), 10)
        update = Update(Location("status", load), "waiting")
    
    Properties:
        - Frozen: Immutable after creation
        - Hashable: Can be used in sets (based on location only)
    """
    location: Location
    value: Any
    
    def __repr__(self) -> str:
        return f"Update({self.location} := {self.value!r})"
    
    def __str__(self) -> str:
        return f"{self.location} := {self.value}"
    
    def __hash__(self) -> int:
        # Hash based on location only (value may not be hashable)
        return hash(self.location)


# ============================================================================
# UpdateConflictError - Conflict exception
# ============================================================================

class UpdateConflictError(Exception):
    """
    Raised when two updates target the same location with different values.
    
    This indicates a semantic error in the ASM model - the same location
    cannot be assigned two different values in the same step.
    
    Attributes:
        location: The conflicting location
        value1: First value assigned
        value2: Second (conflicting) value
    
    Example:
        try:
            updates.add_update(Location("x"), 10)
            updates.add_update(Location("x"), 20)  # Raises!
        except UpdateConflictError as e:
            print(f"Conflict at {e.location}: {e.value1} vs {e.value2}")
    """
    
    def __init__(self, location: Location, value1: Any, value2: Any):
        self.location = location
        self.value1 = value1
        self.value2 = value2
        super().__init__(
            f"Conflicting updates to {location}: "
            f"{value1!r} vs {value2!r}"
        )


# ============================================================================
# UpdateSet - Collection of updates
# ============================================================================

class UpdateSet:
    """
    A collection of updates to be applied atomically.
    
    Features:
    - Conflict detection: same location, different values -> error
    - Idempotent: same location, same value -> OK (kept once)
    - Apply all updates to state at once
    
    Usage:
        updates = UpdateSet()
        
        # Add updates
        updates.add_update(Location("x"), 10)
        updates.add_update(Location("y"), 20)
        
        # Or using Update objects
        updates.add(Update(Location("z"), 30))
        
        # Check for pending updates
        if Location("x") in updates:
            val = updates.get(Location("x"))
        
        # Apply to state
        updates.apply_to(state)
        
        # Iterate
        for update in updates:
            print(update)
    
    Conflict Rules:
        - Same location, same value: OK (idempotent)
        - Same location, different values: UpdateConflictError
        - Values that cannot be compared (TypeError): treated as different
    """
    
    def __init__(self):
        self._updates: Dict[Location, Any] = {}
    
    def add(self, update: Update) -> None:
        """
        Add an Update object.
        
        Args:
            update: The Update to add
            
        Raises:
            UpdateConflictError: If location already has different value
        """
        self.add_update(update.location, update.value)
    
    def add_update(self, location: Location, value: Any) -> None:
        """
        Add update for location.
        
        Args:
            location: The location to update
            value: The new value
            
        Raises:
            UpdateConflictError: If location already has different value
        """
        if location in self._updates:
            existing = self._updates[location]
            
            # Check if values are the same
            try:
                values_equal = (existing == value)
            except TypeError:
                # Cannot compare (e.g., ASMObject vs string)
                # Treat as different -> conflict
                values_equal = False
            
            if not values_equal:
                raise UpdateConflictError(location, existing, value)
            
            # Same value - idempotent, no action needed
            logger.debug(f"Idempotent update: {location} := {value!r}")
        else:
            self._updates[location] = value
            logger.debug(f"Added update: {location} := {value!r}")
    
    def merge(self, other: 'UpdateSet') -> None:
        """
        Merge another UpdateSet into this one.
        
        All updates from other are added to this set.
        
        Args:
            other: UpdateSet to merge from
            
        Raises:
            UpdateConflictError: If any location conflicts
        """
        for location, value in other._updates.items():
            self.add_update(location, value)
        logger.debug(f"Merged {len(other)} updates")
    
    def apply_to(self, state: ASMState) -> None:
        """
        Apply all updates to state.
        
        Args:
            state: The ASMState to modify
        """
        for location, value in self._updates.items():
            state.set(location, value)
        logger.debug(f"Applied {len(self._updates)} updates to state")
    
    def clear(self) -> None:
        """Remove all pending updates."""
        count = len(self._updates)
        self._updates.clear()
        logger.debug(f"Cleared {count} updates")
    
    def get(self, location: Location) -> Any:
        """
        Get pending value for location.
        
        Args:
            location: Location to look up
            
        Returns:
            The pending value, or UNDEF if no update for this location
        """
        return self._updates.get(location, UNDEF)
    
    def contains(self, location: Location) -> bool:
        """
        Check if location has pending update.
        
        Args:
            location: Location to check
            
        Returns:
            True if there's a pending update for this location
        """
        return location in self._updates
    
    def locations(self) -> set:
        """
        Return set of all locations with pending updates.
        
        Returns:
            Set of Location objects
        """
        return set(self._updates.keys())
    
    def __len__(self) -> int:
        """Number of pending updates."""
        return len(self._updates)
    
    def __iter__(self) -> Iterator[Update]:
        """Iterate over Update objects."""
        for location, value in self._updates.items():
            yield Update(location, value)
    
    def __contains__(self, location: Location) -> bool:
        """Check if location has pending update (for 'in' operator)."""
        return location in self._updates
    
    def __repr__(self) -> str:
        return f"UpdateSet({len(self._updates)} updates)"
    
    def __str__(self) -> str:
        if not self._updates:
            return "UpdateSet: (empty)"
        lines = ["UpdateSet:"]
        for location, value in self._updates.items():
            lines.append(f"  {location} := {value!r}")
        return "\n".join(lines)
