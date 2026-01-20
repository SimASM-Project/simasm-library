"""
verification/label.py

Atomic propositions and labeling functions for ASM states.

This module provides:
- Label: An atomic proposition that can hold in a state
- LabelSet: Type alias for immutable sets of labels
- LabelingFunction: Maps ASM states to sets of propositions that hold

These correspond to the labeling components of a transition system:
- AP: Set of atomic propositions (all defined labels)
- L: S -> 2^AP labeling function

References:
- Definition (Transition System of ASM) in thesis
- Baier & Katoen, Principles of Model Checking, Definition 2.1
"""

from dataclasses import dataclass
from typing import Callable, FrozenSet, Dict, Set, Optional, List

from simasm.core.state import ASMState
from simasm.log.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# Type Aliases
# ============================================================================

# Label sets are always immutable for use in traces and comparisons
LabelSet = FrozenSet['Label']


# ============================================================================
# Label - Atomic Proposition
# ============================================================================

@dataclass(frozen=True, eq=True)
class Label:
    """
    An atomic proposition (label) that can hold in a state.
    
    Labels are named boolean predicates over ASM states. They represent
    observable properties such as "QueueEmpty", "ServerBusy", or "Congested".
    
    Properties:
        - Immutable: Created once, never modified
        - Hashable: Can be used in sets and as dict keys
        - Named: Each label has a unique identifying name
    
    Usage:
        # Create labels
        queue_empty = Label("QueueEmpty")
        server_busy = Label("ServerBusy")
        
        # Use in sets
        labels = frozenset({queue_empty, server_busy})
        
        # Check membership
        if queue_empty in labels:
            print("Queue is empty")
    
    Note:
        Labels are just names; the actual predicates are defined
        in the LabelingFunction.
    """
    name: str
    
    def __str__(self) -> str:
        return self.name
    
    def __repr__(self) -> str:
        return f"Label({self.name!r})"
    
    def __lt__(self, other: 'Label') -> bool:
        """Enable sorting of labels by name."""
        if not isinstance(other, Label):
            return NotImplemented
        return self.name < other.name


# ============================================================================
# Predicate Type
# ============================================================================

# A predicate is a function from ASMState to bool
Predicate = Callable[[ASMState], bool]


# ============================================================================
# LabelingFunction - L: S -> 2^AP
# ============================================================================

class LabelingFunction:
    """
    Labeling function L: S -> 2^AP for a transition system.
    
    Maps ASM states to the set of atomic propositions that hold.
    This is the labeling function component of a transition system
    as defined in Definition (TS of ASM).
    
    The labeling function:
    - Maintains a set of atomic propositions AP
    - For each label, stores a predicate function
    - evaluate(state) returns L(state) = {φ ∈ AP | state ⊨ φ}
    
    Usage:
        # Create labeling function
        labeling = LabelingFunction()
        
        # Define atomic propositions
        labeling.define("QueueEmpty", lambda s: s.get_var("queue_len") == 0)
        labeling.define("ServerBusy", lambda s: s.get_var("server_status") == "busy")
        labeling.define("Congested", lambda s: s.get_var("queue_len") >= 3)
        
        # Evaluate on a state
        label_set = labeling.evaluate(state)
        # Returns frozenset of Labels that hold in state
        
        # Access all labels (AP)
        all_labels = labeling.labels
    
    Thread Safety:
        Not thread-safe. Create separate instances for concurrent use.
    """
    
    def __init__(self):
        """Create an empty labeling function."""
        self._predicates: Dict[Label, Predicate] = {}
        self._labels_by_name: Dict[str, Label] = {}
        logger.debug("Created new LabelingFunction")
    
    def define(self, name: str, predicate: Predicate) -> Label:
        """
        Define a new atomic proposition.
        
        Creates a Label with the given name and associates it with
        the predicate function. The predicate should return True
        iff the proposition holds in the given state.
        
        Args:
            name: Unique name for the proposition (e.g., "QueueEmpty")
            predicate: Function ASMState -> bool that evaluates the proposition
        
        Returns:
            The created Label object
        
        Raises:
            ValueError: If a label with this name already exists
        
        Example:
            label = labeling.define(
                "QueueEmpty",
                lambda s: s.get_var("queue_len") == 0
            )
        """
        if name in self._labels_by_name:
            raise ValueError(f"Label '{name}' already defined")
        
        label = Label(name)
        self._labels_by_name[name] = label
        self._predicates[label] = predicate
        
        logger.debug(f"Defined label: {name}")
        return label
    
    def define_from_expression(
        self,
        name: str,
        var_name: str,
        operator: str,
        value: any
    ) -> Label:
        """
        Define a label using a simple comparison expression.
        
        Convenience method for common patterns like "queue_len == 0".
        
        Args:
            name: Label name
            var_name: State variable to check
            operator: Comparison operator ("==", "!=", "<", "<=", ">", ">=")
            value: Value to compare against
        
        Returns:
            The created Label
        
        Raises:
            ValueError: If operator is not supported
        
        Example:
            labeling.define_from_expression("QueueEmpty", "queue_len", "==", 0)
            labeling.define_from_expression("Congested", "queue_len", ">=", 3)
        """
        operators = {
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
        }
        
        if operator not in operators:
            raise ValueError(f"Unsupported operator: {operator}. Use one of: {list(operators.keys())}")
        
        op_func = operators[operator]
        predicate = lambda s, vn=var_name, v=value, op=op_func: op(s.get_var(vn), v)
        
        return self.define(name, predicate)
    
    def get_label(self, name: str) -> Optional[Label]:
        """
        Get a label by name.
        
        Args:
            name: The label name to look up
        
        Returns:
            The Label if found, None otherwise
        """
        return self._labels_by_name.get(name)
    
    def has_label(self, name: str) -> bool:
        """
        Check if a label with the given name exists.
        
        Args:
            name: The label name to check
        
        Returns:
            True if the label exists
        """
        return name in self._labels_by_name
    
    def evaluate(self, state: ASMState) -> LabelSet:
        """
        Compute L(state) - the set of propositions that hold in state.
        
        Evaluates each defined predicate against the state and returns
        the frozen set of labels whose predicates return True.
        
        Args:
            state: The ASM state to evaluate
        
        Returns:
            Frozen set of Labels that hold in the state
        
        Example:
            labels = labeling.evaluate(state)
            if Label("QueueEmpty") in labels:
                print("Queue is empty")
        """
        result: Set[Label] = set()
        
        for label, predicate in self._predicates.items():
            try:
                if predicate(state):
                    result.add(label)
            except Exception as e:
                logger.warning(f"Error evaluating predicate for {label}: {e}")
                # Predicate errors mean the label does not hold
        
        return frozenset(result)
    
    def evaluate_single(self, state: ASMState, label: Label) -> bool:
        """
        Check if a single label holds in the given state.
        
        Args:
            state: The ASM state to evaluate
            label: The label to check
        
        Returns:
            True if the label's predicate returns True
        
        Raises:
            KeyError: If the label is not defined
        """
        if label not in self._predicates:
            raise KeyError(f"Label {label} not defined in this labeling function")
        
        try:
            return self._predicates[label](state)
        except Exception as e:
            logger.warning(f"Error evaluating predicate for {label}: {e}")
            return False
    
    @property
    def labels(self) -> FrozenSet[Label]:
        """
        Return all defined labels (the set AP).
        
        Returns:
            Frozen set of all Label objects
        """
        return frozenset(self._predicates.keys())
    
    @property
    def label_names(self) -> FrozenSet[str]:
        """
        Return all label names.
        
        Returns:
            Frozen set of label name strings
        """
        return frozenset(self._labels_by_name.keys())
    
    def __len__(self) -> int:
        """Number of defined labels."""
        return len(self._predicates)
    
    def __contains__(self, item) -> bool:
        """Check if a label or label name is defined."""
        if isinstance(item, Label):
            return item in self._predicates
        elif isinstance(item, str):
            return item in self._labels_by_name
        return False
    
    def __repr__(self) -> str:
        return f"LabelingFunction({len(self)} labels)"
    
    def __str__(self) -> str:
        if not self._labels_by_name:
            return "LabelingFunction: (empty)"
        
        names = sorted(self._labels_by_name.keys())
        return f"LabelingFunction: {{{', '.join(names)}}}"


# ============================================================================
# Helper Functions
# ============================================================================

def empty_label_set() -> LabelSet:
    """
    Return an empty label set.
    
    Convenience function for creating empty LabelSet.
    
    Returns:
        Empty frozen set of labels
    """
    return frozenset()


def label_set(*labels: Label) -> LabelSet:
    """
    Create a label set from the given labels.
    
    Convenience function for creating LabelSet from labels.
    
    Args:
        *labels: Label objects to include
    
    Returns:
        Frozen set containing the labels
    
    Example:
        ls = label_set(queue_empty, server_busy)
    """
    return frozenset(labels)


def label_set_from_names(labeling: LabelingFunction, *names: str) -> LabelSet:
    """
    Create a label set from label names.
    
    Args:
        labeling: The LabelingFunction containing the labels
        *names: Label names to include
    
    Returns:
        Frozen set of Labels
    
    Raises:
        KeyError: If any name is not defined
    
    Example:
        ls = label_set_from_names(labeling, "QueueEmpty", "ServerBusy")
    """
    labels = []
    for name in names:
        label = labeling.get_label(name)
        if label is None:
            raise KeyError(f"Label '{name}' not defined")
        labels.append(label)
    return frozenset(labels)


def labels_equal(ls1: LabelSet, ls2: LabelSet) -> bool:
    """
    Check if two label sets are equal.
    
    Args:
        ls1: First label set
        ls2: Second label set
    
    Returns:
        True if the sets contain the same labels
    """
    return ls1 == ls2


def format_label_set(ls: LabelSet) -> str:
    """
    Format a label set as a readable string.
    
    Args:
        ls: Label set to format
    
    Returns:
        String like "{QueueEmpty, ServerBusy}" or "{}" for empty
    
    Example:
        print(format_label_set(labels))  # "{QueueEmpty, ServerBusy}"
    """
    if not ls:
        return "{}"
    names = sorted(label.name for label in ls)
    return "{" + ", ".join(names) + "}"