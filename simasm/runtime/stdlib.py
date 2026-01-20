"""
runtime/stdlib.py

Standard library functions (lib.*) for SimASM.

All functions are accessed via lib.func_name() in SimASM code.
The TermEvaluator resolves LibCallTerm nodes by calling methods on this class.

Design decisions:
- List operations MUTATE in place (Python style)
- Key parameters are attribute names (strings)
- Predicates are state function names (strings)
"""

from typing import Any, List, Optional, Callable, TYPE_CHECKING

from simasm.log.logger import get_logger

if TYPE_CHECKING:
    from simasm.core.state import ASMState
    from simasm.core.rules import RuleRegistry, RuleEvaluator
    from simasm.core.terms import Environment

logger = get_logger(__name__)


class StdlibError(Exception):
    """Raised when a stdlib function fails."""
    pass


class StandardLibrary:
    """
    Standard library functions for SimASM.
    
    Provides lib.* functions accessible from SimASM code.
    
    Usage:
        stdlib = StandardLibrary(state, rules)
        stdlib.add(my_list, item)      # Mutates my_list
        val = stdlib.length(my_list)   # Returns length
        
    Note: Some functions (like apply_rule, filter) need access to
    the rule evaluator, which is set after construction via set_evaluator().
    """
    
    def __init__(self, state: 'ASMState', rules: 'RuleRegistry'):
        """
        Initialize StandardLibrary.
        
        Args:
            state: ASM state for function lookups (predicates, etc.)
            rules: Rule registry for apply_rule
        """
        self._state = state
        self._rules = rules
        self._evaluator: Optional['RuleEvaluator'] = None
        logger.debug("Created StandardLibrary")
    
    def set_evaluator(self, evaluator: 'RuleEvaluator') -> None:
        """
        Set the rule evaluator (for apply_rule).
        
        Must be called after RuleEvaluator is constructed.
        """
        self._evaluator = evaluator
        logger.debug("Set evaluator for StandardLibrary")
    
    # =========================================================================
    # List Operations (mutating, Python style)
    # =========================================================================
    
    def add(self, lst: List, item: Any) -> None:
        """
        Append item to end of list.
        
        Mutates the list in place.
        
        Example:
            lib.add(queue, load)
        """
        if not isinstance(lst, list):
            raise StdlibError(f"lib.add: expected list, got {type(lst).__name__}")
        lst.append(item)
        logger.debug(f"lib.add: appended {item!r}, length now {len(lst)}")
    
    def pop(self, lst: List) -> Any:
        """
        Remove and return first item from list.
        
        Mutates the list in place.
        
        Example:
            let next = lib.pop(queue)
        
        Raises:
            StdlibError: If list is empty
        """
        if not isinstance(lst, list):
            raise StdlibError(f"lib.pop: expected list, got {type(lst).__name__}")
        if len(lst) == 0:
            raise StdlibError("lib.pop: cannot pop from empty list")
        item = lst.pop(0)
        logger.debug(f"lib.pop: removed {item!r}, length now {len(lst)}")
        return item
    
    def remove(self, lst: List, item: Any) -> None:
        """
        Remove first occurrence of item from list.
        
        Mutates the list in place.
        
        Example:
            lib.remove(FEL, event)
        
        Raises:
            StdlibError: If item not found
        """
        if not isinstance(lst, list):
            raise StdlibError(f"lib.remove: expected list, got {type(lst).__name__}")
        try:
            lst.remove(item)
            logger.debug(f"lib.remove: removed {item!r}, length now {len(lst)}")
        except ValueError:
            raise StdlibError(f"lib.remove: item not found: {item!r}")
    
    def get(self, lst: List, index: int) -> Any:
        """
        Get item at index (0-based).
        
        Example:
            let first = lib.get(queue, 0)
        
        Raises:
            StdlibError: If index out of bounds
        """
        if not isinstance(lst, list):
            raise StdlibError(f"lib.get: expected list, got {type(lst).__name__}")
        if not isinstance(index, int):
            raise StdlibError(f"lib.get: index must be int, got {type(index).__name__}")
        if index < 0 or index >= len(lst):
            raise StdlibError(f"lib.get: index {index} out of bounds for list of length {len(lst)}")
        return lst[index]
    
    def length(self, lst: List) -> int:
        """
        Return length of list.
        
        Example:
            if lib.length(queue) > 0 then ...
        """
        if not isinstance(lst, list):
            raise StdlibError(f"lib.length: expected list, got {type(lst).__name__}")
        return len(lst)
    
    def sort(self, lst: List, key: str, *additional_keys: str) -> None:
        """
        Sort list in place by key function(s).

        The key parameter(s) specify how to extract sort keys from items.
        For ASMObjects, keys are looked up as dynamic functions in state.
        For regular Python objects, falls back to attribute lookup.

        When multiple keys are provided, they are used for tie-breaking:
        the first key is the primary sort, second key breaks ties, etc.

        Example:
            # Sort by single key (dynamic function for ASMObjects)
            lib.sort(FEL, "event_scheduled_time")

            # Sort by multiple keys for tie-breaking
            lib.sort(FEL, "event_scheduled_time", "event_priority")
            # This sorts primarily by time, then by priority for ties

            # Sort by attribute (Python objects)
            lib.sort(events, "time")

        Raises:
            StdlibError: If key function/attribute doesn't exist or comparison fails
        """
        if not isinstance(lst, list):
            raise StdlibError(f"lib.sort: expected list, got {type(lst).__name__}")
        if len(lst) == 0:
            return

        # Import here to avoid circular import
        from simasm.core.state import ASMObject, UNDEF

        # Combine all keys into a list
        all_keys = [key] + list(additional_keys)

        def get_single_key(item: Any, key_name: str) -> Any:
            # For ASMObjects, try dynamic function lookup in state first
            if isinstance(item, ASMObject):
                value = self._state.get_func(key_name, (item,))
                if value is not UNDEF:
                    return value
                # Fall through to attribute lookup if function not found

            # Fallback: try Python attribute lookup
            try:
                return getattr(item, key_name)
            except AttributeError:
                if isinstance(item, ASMObject):
                    raise StdlibError(
                        f"lib.sort: neither dynamic function '{key_name}' nor attribute found for {item}"
                    )
                raise StdlibError(f"lib.sort: attribute '{key_name}' not found on {type(item).__name__}")

        def get_key(item: Any) -> tuple:
            # Return tuple of all key values for multi-key sorting
            return tuple(get_single_key(item, k) for k in all_keys)

        try:
            lst.sort(key=get_key)
            if additional_keys:
                logger.debug(f"lib.sort: sorted by {all_keys}")
            else:
                logger.debug(f"lib.sort: sorted by '{key}'")
        except TypeError as e:
            raise StdlibError(f"lib.sort: comparison failed: {e}")
    
    def filter(self, lst: List, pred: str) -> List:
        """
        Filter list by predicate (state function name).
        
        The predicate is a dynamic function name in state.
        Returns a NEW list (does not mutate original).
        
        Example:
            dynamic function is_enabled(e: Edge): Bool
            let enabled = lib.filter(edges, "is_enabled")
        
        Args:
            lst: List to filter
            pred: Name of a dynamic function that takes one arg and returns Bool
        
        Returns:
            New list containing only items where pred(item) is truthy
        """
        if not isinstance(lst, list):
            raise StdlibError(f"lib.filter: expected list, got {type(lst).__name__}")
        
        result = []
        for item in lst:
            # Look up pred(item) in state
            value = self._state.get_func(pred, (item,))
            if value:
                result.append(item)
        
        logger.debug(f"lib.filter: {len(result)}/{len(lst)} items passed predicate '{pred}'")
        return result
    
    # =========================================================================
    # Selection Operations
    # =========================================================================
    
    def min_by(self, lst: List, key: str) -> Any:
        """
        Return item with minimum key value.
        
        For ASMObjects, the key is looked up as a dynamic function in state.
        For regular Python objects, falls back to attribute lookup.
        
        Example:
            let next = lib.min_by(FEL, "event_scheduled_time")  # Event with earliest time
        
        Raises:
            StdlibError: If list is empty or key function/attribute doesn't exist
        """
        if not isinstance(lst, list):
            raise StdlibError(f"lib.min_by: expected list, got {type(lst).__name__}")
        if len(lst) == 0:
            raise StdlibError("lib.min_by: cannot find min of empty list")
        
        # Import here to avoid circular import
        from simasm.core.state import ASMObject, UNDEF
        
        def get_key(item: Any) -> Any:
            # For ASMObjects, try dynamic function lookup in state first
            if isinstance(item, ASMObject):
                value = self._state.get_func(key, (item,))
                if value is not UNDEF:
                    return value
            
            # Fallback: try Python attribute lookup
            try:
                return getattr(item, key)
            except AttributeError:
                if isinstance(item, ASMObject):
                    raise StdlibError(
                        f"lib.min_by: neither dynamic function '{key}' nor attribute found for {item}"
                    )
                raise StdlibError(f"lib.min_by: attribute '{key}' not found on {type(item).__name__}")
        
        try:
            result = min(lst, key=get_key)
            logger.debug(f"lib.min_by: found item with {key}={get_key(result)!r}")
            return result
        except TypeError as e:
            raise StdlibError(f"lib.min_by: comparison failed: {e}")
    
    def max_by(self, lst: List, key: str) -> Any:
        """
        Return item with maximum key value.
        
        For ASMObjects, the key is looked up as a dynamic function in state.
        For regular Python objects, falls back to attribute lookup.
        
        Example:
            let highest = lib.max_by(items, "priority")
        
        Raises:
            StdlibError: If list is empty or key function/attribute doesn't exist
        """
        if not isinstance(lst, list):
            raise StdlibError(f"lib.max_by: expected list, got {type(lst).__name__}")
        if len(lst) == 0:
            raise StdlibError("lib.max_by: cannot find max of empty list")
        
        # Import here to avoid circular import
        from simasm.core.state import ASMObject, UNDEF
        
        def get_key(item: Any) -> Any:
            # For ASMObjects, try dynamic function lookup in state first
            if isinstance(item, ASMObject):
                value = self._state.get_func(key, (item,))
                if value is not UNDEF:
                    return value
            
            # Fallback: try Python attribute lookup
            try:
                return getattr(item, key)
            except AttributeError:
                if isinstance(item, ASMObject):
                    raise StdlibError(
                        f"lib.max_by: neither dynamic function '{key}' nor attribute found for {item}"
                    )
                raise StdlibError(f"lib.max_by: attribute '{key}' not found on {type(item).__name__}")
        
        try:
            result = max(lst, key=get_key)
            logger.debug(f"lib.max_by: found item with {key}={get_key(result)!r}")
            return result
        except TypeError as e:
            raise StdlibError(f"lib.max_by: comparison failed: {e}")
    
    # =========================================================================
    # Tuple Access
    # =========================================================================
    
    def first(self, tup: tuple) -> Any:
        """
        Get first element of tuple (index 0).
        
        Example:
            let vertex = lib.first(event)  # event = (vertex, time, priority)
        """
        if not isinstance(tup, (tuple, list)):
            raise StdlibError(f"lib.first: expected tuple/list, got {type(tup).__name__}")
        if len(tup) < 1:
            raise StdlibError("lib.first: tuple/list is empty")
        return tup[0]
    
    def second(self, tup: tuple) -> Any:
        """
        Get second element of tuple (index 1).
        
        Example:
            let time = lib.second(event)  # event = (vertex, time, priority)
        """
        if not isinstance(tup, (tuple, list)):
            raise StdlibError(f"lib.second: expected tuple/list, got {type(tup).__name__}")
        if len(tup) < 2:
            raise StdlibError(f"lib.second: tuple/list has only {len(tup)} elements")
        return tup[1]
    
    def third(self, tup: tuple) -> Any:
        """
        Get third element of tuple (index 2).
        
        Example:
            let priority = lib.third(event)  # event = (vertex, time, priority)
        """
        if not isinstance(tup, (tuple, list)):
            raise StdlibError(f"lib.third: expected tuple/list, got {type(tup).__name__}")
        if len(tup) < 3:
            raise StdlibError(f"lib.third: tuple/list has only {len(tup)} elements")
        return tup[2]
    
    def last(self, tup: tuple) -> Any:
        """
        Get last element of tuple (index -1).
        
        Example:
            let final = lib.last(sequence)
        """
        if not isinstance(tup, (tuple, list)):
            raise StdlibError(f"lib.last: expected tuple/list, got {type(tup).__name__}")
        if len(tup) < 1:
            raise StdlibError("lib.last: tuple/list is empty")
        return tup[-1]
    
    # =========================================================================
    # Set-like Operations (on List)
    # =========================================================================
    
    def set_add(self, lst: List, item: Any) -> None:
        """
        Add item to list only if not already present.
        
        Mutates the list in place.
        
        Example:
            lib.set_add(visited, node)
        """
        if not isinstance(lst, list):
            raise StdlibError(f"lib.set_add: expected list, got {type(lst).__name__}")
        if item not in lst:
            lst.append(item)
            logger.debug(f"lib.set_add: added {item!r}")
        else:
            logger.debug(f"lib.set_add: {item!r} already present")
    
    def set_contains(self, lst: List, item: Any) -> bool:
        """
        Check if item is in list.
        
        Example:
            if lib.set_contains(visited, node) then ...
        """
        if not isinstance(lst, list):
            raise StdlibError(f"lib.set_contains: expected list, got {type(lst).__name__}")
        return item in lst
    
    def set_remove(self, lst: List, item: Any) -> None:
        """
        Remove item from list if present (no error if absent).
        
        Mutates the list in place.
        Unlike lib.remove, this does NOT raise error if item not found.
        
        Example:
            lib.set_remove(FEL, cancelled_event)
        """
        if not isinstance(lst, list):
            raise StdlibError(f"lib.set_remove: expected list, got {type(lst).__name__}")
        try:
            lst.remove(item)
            logger.debug(f"lib.set_remove: removed {item!r}")
        except ValueError:
            logger.debug(f"lib.set_remove: {item!r} not found (ignored)")
    
    # =========================================================================
    # Rule Operations
    # =========================================================================
    
    def apply_rule(self, rule_ref: str, params: List[Any]) -> None:
        """
        Invoke a rule by name with given parameters.
        
        Used for dynamic dispatch when rule name is stored in state.
        
        Example:
            dynamic function event_rule(e: Event): Rule
            event_rule(arrive_event) := "handle_arrive"
            
            lib.apply_rule(event_rule(e), [])  # Calls handle_arrive()
        
        Args:
            rule_ref: Rule name (string)
            params: List of parameter values
        
        Raises:
            StdlibError: If evaluator not set, rule not found, or arity mismatch
        """
        if self._evaluator is None:
            raise StdlibError("lib.apply_rule: evaluator not set")
        
        if not isinstance(rule_ref, str):
            raise StdlibError(f"lib.apply_rule: rule_ref must be string, got {type(rule_ref).__name__}")
        
        if not isinstance(params, list):
            raise StdlibError(f"lib.apply_rule: params must be list, got {type(params).__name__}")
        
        logger.debug(f"lib.apply_rule: invoking {rule_ref} with {len(params)} params")
        
        # Import here to avoid circular import
        from simasm.core.terms import Environment
        
        # Create fresh environment for rule call
        env = Environment()
        
        # Invoke rule via evaluator
        updates = self._evaluator.invoke_rule(rule_ref, params, env)
        
        # Apply updates to state
        updates.apply_to(self._state)
        
        logger.debug(f"lib.apply_rule: applied {len(updates)} updates")
