"""
verification/trace.py

Trace representation and stutter equivalence operations.

This module provides:
- Trace: Sequence of label sets from a path in a transition system
- no_stutter_trace: Remove consecutive duplicate labels (Definition 12)
- traces_stutter_equivalent: Check stutter equivalence (Proposition 1)

Traces capture the observable behavior of a transition system. Two traces
are stutter equivalent if they have the same no-stutter form.

References:
- Definition (Trace of ASM in Transition System) in thesis
- Definition 12 (No-Stutter Trace)
- Proposition 1 (Stutter Equivalence via No-Stutter Trace)
- Baier & Katoen, Principles of Model Checking, Section 7.2
"""

from dataclasses import dataclass, field
from typing import List, Iterator, Optional, Tuple

from simasm.log.logger import get_logger
from .label import LabelSet, Label, format_label_set

logger = get_logger(__name__)


# ============================================================================
# Trace - Sequence of Label Sets
# ============================================================================

@dataclass
class Trace:
    """
    A trace (sequence of label sets) from a path in a transition system.
    
    Corresponds to trace(π) = L(A₀) -> L(A₁) -> L(A₂) -> ... from
    Definition (Trace of ASM in Transition System).
    
    Each position in the trace holds a LabelSet (frozenset of Labels)
    representing the atomic propositions that hold at that state.
    
    Properties:
        - Ordered: Maintains sequence order
        - Immutable elements: Each LabelSet is frozen
        - Indexable: Supports random access
        - Iterable: Can iterate over label sets
    
    Usage:
        trace = Trace()
        trace.append(frozenset({Label("QueueEmpty")}))
        trace.append(frozenset({Label("ServerBusy")}))
        
        # Access elements
        first = trace[0]
        last = trace.last()
        
        # Check stutter
        if trace.is_stutter_step(0):
            print("First transition is a stutter step")
        
        # Get length
        print(f"Trace has {len(trace)} positions")
    """
    _labels: List[LabelSet] = field(default_factory=list)
    
    def append(self, label_set: LabelSet) -> None:
        """
        Append a label set to the trace.
        
        Args:
            label_set: Frozen set of Labels to append
        """
        self._labels.append(label_set)
    
    def extend(self, label_sets: List[LabelSet]) -> None:
        """
        Extend trace with multiple label sets.
        
        Args:
            label_sets: List of label sets to append
        """
        self._labels.extend(label_sets)
    
    def __len__(self) -> int:
        """Number of positions in the trace."""
        return len(self._labels)
    
    def __getitem__(self, index: int) -> LabelSet:
        """
        Get label set at position index.
        
        Args:
            index: Position (0-indexed, supports negative indexing)
        
        Returns:
            The LabelSet at that position
        
        Raises:
            IndexError: If index is out of bounds
        """
        return self._labels[index]
    
    def __iter__(self) -> Iterator[LabelSet]:
        """Iterate over label sets."""
        return iter(self._labels)
    
    def __eq__(self, other: object) -> bool:
        """
        Check trace equality.
        
        Two traces are equal if they have the same label sets
        in the same order. Used for checking stutter equivalence
        via Proposition 1: σ_A ≜ σ_B ⟺ ns(σ_A) = ns(σ_B)
        
        Args:
            other: Object to compare with
        
        Returns:
            True if traces are equal
        """
        if not isinstance(other, Trace):
            return NotImplemented
        return self._labels == other._labels
    
    def __hash__(self) -> int:
        """
        Hash for use in sets/dicts.
        
        Converts internal list to tuple for hashing.
        """
        return hash(tuple(self._labels))
    
    def last(self) -> LabelSet:
        """
        Return the last label set (Lemma 1).
        
        For any non-empty finite trace, last(ns(σ)) = last(σ).
        
        Returns:
            The final LabelSet in the trace
        
        Raises:
            IndexError: If trace is empty
        """
        if not self._labels:
            raise IndexError("Cannot get last element of empty trace")
        return self._labels[-1]
    
    def first(self) -> LabelSet:
        """
        Return the first label set.
        
        Returns:
            The first LabelSet in the trace
        
        Raises:
            IndexError: If trace is empty
        """
        if not self._labels:
            raise IndexError("Cannot get first element of empty trace")
        return self._labels[0]
    
    def is_empty(self) -> bool:
        """Check if trace has no elements."""
        return len(self._labels) == 0
    
    def is_stutter_step(self, index: int) -> bool:
        """
        Check if transition at index is a stutter step (Definition: Stutter Step).
        
        A transition A_i -> A_{i+1} is a stutter step iff L(A_i) = L(A_{i+1}).
        
        Args:
            index: Position to check (checks transition from index to index+1)
        
        Returns:
            True if L[index] == L[index+1]
        
        Raises:
            IndexError: If index or index+1 is out of bounds
        """
        if index < 0 or index + 1 >= len(self._labels):
            raise IndexError(f"Cannot check stutter at index {index} for trace of length {len(self._labels)}")
        return self._labels[index] == self._labels[index + 1]
    
    def copy(self) -> 'Trace':
        """
        Create a copy of this trace.
        
        Returns:
            New Trace with same label sets
        """
        new_trace = Trace()
        new_trace._labels = self._labels.copy()
        return new_trace
    
    def slice(self, start: int, end: Optional[int] = None) -> 'Trace':
        """
        Get a slice of the trace.
        
        Args:
            start: Start index (inclusive)
            end: End index (exclusive), None for rest of trace
        
        Returns:
            New Trace containing the slice
        """
        new_trace = Trace()
        if end is None:
            new_trace._labels = self._labels[start:]
        else:
            new_trace._labels = self._labels[start:end]
        return new_trace
    
    def to_list(self) -> List[LabelSet]:
        """
        Convert trace to list of label sets.
        
        Returns:
            Copy of internal list
        """
        return self._labels.copy()
    
    def __repr__(self) -> str:
        if len(self._labels) == 0:
            return "Trace([])"
        elif len(self._labels) <= 3:
            labels_str = " -> ".join(format_label_set(ls) for ls in self._labels)
            return f"Trace([{labels_str}])"
        else:
            first = format_label_set(self._labels[0])
            last = format_label_set(self._labels[-1])
            return f"Trace([{first} -> ... -> {last}], len={len(self._labels)})"
    
    def __str__(self) -> str:
        if len(self._labels) == 0:
            return "(empty)"  # Empty trace
        return " -> ".join(format_label_set(ls) for ls in self._labels)


# ============================================================================
# No-Stutter Trace (Definition 12)
# ============================================================================

def no_stutter_trace(trace: Trace) -> Trace:
    """
    Compute the no-stutter trace ns(σ) (Definition 12).
    
    Retains only positions where the label differs from the preceding label.
    The first position (index 0) is always retained.
    
    For a trace σ = Q₀ -> Q₁ -> Q₂ -> ... -> Q_n, the no-stutter trace is:
    ns(σ) = Q_{i₀} -> Q_{i₁} -> Q_{i₂} -> ...
    
    where:
    - i₀ = 0 (always retained)
    - i_k is the smallest index > i_{k-1} such that Q_{i_k} ≠ Q_{i_{k-1}}
    
    Example:
        σ = {p} -> {p} -> {p} -> {q} -> {q} -> {p,q} -> {p,q} -> {q}
        ns(σ) = {p} -> {q} -> {p,q} -> {q}
    
    Args:
        trace: Input trace
    
    Returns:
        New trace with consecutive duplicates removed
    """
    if trace.is_empty():
        return Trace()
    
    result = Trace()
    result.append(trace[0])  # First position always retained
    
    for i in range(1, len(trace)):
        if trace[i] != trace[i - 1]:
            result.append(trace[i])
    
    return result


def is_stutter_free(trace: Trace) -> bool:
    """
    Check if a trace has no consecutive duplicate labels.
    
    A trace is stutter-free if ns(trace) == trace.
    
    Args:
        trace: Trace to check
    
    Returns:
        True if trace has no stutter steps
    """
    if len(trace) <= 1:
        return True
    
    for i in range(len(trace) - 1):
        if trace[i] == trace[i + 1]:
            return False
    return True


# ============================================================================
# Stutter Equivalence (Proposition 1)
# ============================================================================

def traces_stutter_equivalent(trace_a: Trace, trace_b: Trace) -> bool:
    """
    Check if two traces are stutter equivalent (Proposition 1).
    
    Two traces σ_A and σ_B are stutter equivalent, denoted σ_A ≜ σ_B,
    if and only if their no-stutter traces are equal:
    
        σ_A ≜ σ_B ⟺ ns(σ_A) = ns(σ_B)
    
    Intuitively, stutter equivalent traces have the same sequence of
    distinct label sets, possibly with different repetition counts.
    
    Args:
        trace_a: First trace
        trace_b: Second trace
    
    Returns:
        True iff the traces are stutter equivalent
    
    Example:
        σ_A = {idle} -> {idle} -> {idle} -> {busy} -> {busy}
        σ_B = {idle} -> {busy} -> {busy} -> {busy} -> {busy}
        
        ns(σ_A) = {idle} -> {busy}
        ns(σ_B) = {idle} -> {busy}
        
        Therefore σ_A ≜ σ_B (stutter equivalent)
    """
    ns_a = no_stutter_trace(trace_a)
    ns_b = no_stutter_trace(trace_b)
    return ns_a == ns_b


# ============================================================================
# No-Stutter Extension (Lemma 2)
# ============================================================================

def extend_no_stutter(ns_trace: Trace, new_label: LabelSet) -> Trace:
    """
    Extend a no-stutter trace with a new label (Lemma 2).
    
    Given a no-stutter trace ns(σ) and a new label Q:
    1. If Q equals the last element of ns(σ), return ns(σ) unchanged
    2. If Q differs from the last element, return ns(σ) -> Q
    
    This operation is used when building no-stutter traces incrementally
    during product system execution.
    
    Args:
        ns_trace: A no-stutter trace (assumed to be stutter-free)
        new_label: Label to append
    
    Returns:
        Extended no-stutter trace (new Trace object)
    
    Note:
        If ns_trace is empty, the new_label is simply returned as a
        single-element trace.
    """
    result = ns_trace.copy()
    
    if result.is_empty():
        result.append(new_label)
    elif result.last() != new_label:
        result.append(new_label)
    # else: new_label equals last, so don't append (stutter)
    
    return result


# ============================================================================
# Trace Prefix Operations
# ============================================================================

def is_prefix(prefix: Trace, trace: Trace) -> bool:
    """
    Check if one trace is a prefix of another.
    
    Args:
        prefix: Potential prefix trace
        trace: Full trace
    
    Returns:
        True if prefix is a prefix of trace
    """
    if len(prefix) > len(trace):
        return False
    
    for i in range(len(prefix)):
        if prefix[i] != trace[i]:
            return False
    return True


def common_prefix(trace_a: Trace, trace_b: Trace) -> Trace:
    """
    Compute the longest common prefix of two traces.
    
    Args:
        trace_a: First trace
        trace_b: Second trace
    
    Returns:
        Longest common prefix (may be empty)
    """
    result = Trace()
    min_len = min(len(trace_a), len(trace_b))
    
    for i in range(min_len):
        if trace_a[i] == trace_b[i]:
            result.append(trace_a[i])
        else:
            break
    
    return result


# ============================================================================
# Trace Comparison Utilities
# ============================================================================

def trace_divergence_point(trace_a: Trace, trace_b: Trace) -> Optional[int]:
    """
    Find the first index where two traces differ.
    
    Args:
        trace_a: First trace
        trace_b: Second trace
    
    Returns:
        Index where traces first differ, or None if one is prefix of other
    """
    min_len = min(len(trace_a), len(trace_b))
    
    for i in range(min_len):
        if trace_a[i] != trace_b[i]:
            return i
    
    # One is prefix of the other
    if len(trace_a) != len(trace_b):
        return min_len
    
    # Traces are identical
    return None


def no_stutter_divergence_point(trace_a: Trace, trace_b: Trace) -> Optional[int]:
    """
    Find the first index where no-stutter traces differ.
    
    Useful for debugging stutter equivalence failures.
    
    Args:
        trace_a: First trace
        trace_b: Second trace
    
    Returns:
        Index in no-stutter traces where they first differ
    """
    ns_a = no_stutter_trace(trace_a)
    ns_b = no_stutter_trace(trace_b)
    return trace_divergence_point(ns_a, ns_b)


# ============================================================================
# Trace Construction Helpers
# ============================================================================

def trace_from_labels(*label_sets: LabelSet) -> Trace:
    """
    Create a trace from label sets.
    
    Convenience function for creating traces in tests.
    
    Args:
        *label_sets: Label sets in sequence
    
    Returns:
        New Trace containing the label sets
    
    Example:
        trace = trace_from_labels(
            frozenset({Label("idle")}),
            frozenset({Label("busy")}),
            frozenset({Label("idle")})
        )
    """
    trace = Trace()
    for ls in label_sets:
        trace.append(ls)
    return trace


def trace_from_label_names(labeling, *name_sequences: Tuple[str, ...]) -> Trace:
    """
    Create a trace from sequences of label names.
    
    Each argument is a tuple of label names that should hold at that position.
    
    Args:
        labeling: LabelingFunction containing the label definitions
        *name_sequences: Tuples of label names for each position
    
    Returns:
        New Trace
    
    Example:
        trace = trace_from_label_names(
            labeling,
            ("QueueEmpty", "ServerIdle"),
            ("QueueEmpty", "ServerBusy"),
            ("QueueNonEmpty", "ServerBusy")
        )
    """
    trace = Trace()
    for names in name_sequences:
        labels = set()
        for name in names:
            label = labeling.get_label(name)
            if label is None:
                raise KeyError(f"Label '{name}' not defined in labeling function")
            labels.add(label)
        trace.append(frozenset(labels))
    return trace


# ============================================================================
# Trace Statistics
# ============================================================================

def count_stutter_steps(trace: Trace) -> int:
    """
    Count the number of stutter steps in a trace.
    
    Args:
        trace: Trace to analyze
    
    Returns:
        Number of transitions where L[i] == L[i+1]
    """
    if len(trace) <= 1:
        return 0
    
    count = 0
    for i in range(len(trace) - 1):
        if trace[i] == trace[i + 1]:
            count += 1
    return count


def stutter_ratio(trace: Trace) -> float:
    """
    Compute the ratio of stutter steps to total transitions.
    
    Args:
        trace: Trace to analyze
    
    Returns:
        Fraction of transitions that are stutter steps (0.0 to 1.0)
        Returns 0.0 for traces with 0 or 1 elements
    """
    if len(trace) <= 1:
        return 0.0
    
    total_transitions = len(trace) - 1
    stutter_count = count_stutter_steps(trace)
    return stutter_count / total_transitions


def distinct_labels(trace: Trace) -> int:
    """
    Count the number of distinct label sets in a trace.
    
    Args:
        trace: Trace to analyze
    
    Returns:
        Number of unique label sets
    """
    return len(set(trace._labels))