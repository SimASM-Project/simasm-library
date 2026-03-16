"""
verification/numeric_trace.py

Numeric timeseries trace representation for visualization.

This module provides data structures for capturing numeric observable values
over simulation time, enabling timeseries visualization of simulation runs.

Provides:
- NumericTrace: Sequence of (time, value) pairs from a simulation run
- NumericObservable: Definition of a numeric observable expression
- NumericTraceResult: Collection of numeric traces from a verification run
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Iterator


@dataclass
class NumericTrace:
    """
    Numeric timeseries trace from simulation.

    Stores a sequence of (time, value) pairs representing the evolution
    of a numeric observable over simulation time.

    Usage:
        trace = NumericTrace("total_busy")
        trace.append(0.0, 5)
        trace.append(1.5, 6)
        trace.append(2.3, 5)

        # Access as lists
        times = trace.times
        values = trace.values

        # Get no-stutter version
        ns_trace = trace.no_stutter_trace()
    """
    name: str
    _points: List[Tuple[float, float]] = field(default_factory=list)

    def append(self, time: float, value: float) -> None:
        """
        Append a (time, value) point to the trace.

        Args:
            time: Simulation time
            value: Observable value at that time
        """
        self._points.append((time, value))

    def extend(self, points: List[Tuple[float, float]]) -> None:
        """
        Extend trace with multiple points.

        Args:
            points: List of (time, value) tuples
        """
        self._points.extend(points)

    @property
    def points(self) -> List[Tuple[float, float]]:
        """Return list of (time, value) pairs."""
        return self._points.copy()

    @property
    def times(self) -> List[float]:
        """Return list of time values."""
        return [t for t, _ in self._points]

    @property
    def values(self) -> List[float]:
        """Return list of observable values."""
        return [v for _, v in self._points]

    def __len__(self) -> int:
        """Number of points in the trace."""
        return len(self._points)

    def __getitem__(self, index: int) -> Tuple[float, float]:
        """Get point at index."""
        return self._points[index]

    def __iter__(self) -> Iterator[Tuple[float, float]]:
        """Iterate over (time, value) pairs."""
        return iter(self._points)

    def is_empty(self) -> bool:
        """Check if trace has no points."""
        return len(self._points) == 0

    def first(self) -> Tuple[float, float]:
        """Return the first point."""
        if not self._points:
            raise IndexError("Cannot get first element of empty trace")
        return self._points[0]

    def last(self) -> Tuple[float, float]:
        """Return the last point."""
        if not self._points:
            raise IndexError("Cannot get last element of empty trace")
        return self._points[-1]

    def no_stutter_trace(self) -> 'NumericTrace':
        """
        Remove consecutive duplicate values.

        Returns a new trace containing only points where the value
        differs from the previous point. The first point is always retained.

        This is the numeric analog of the label-based no_stutter_trace()
        from verification/trace.py.

        Returns:
            New NumericTrace with consecutive duplicates removed
        """
        if self.is_empty():
            return NumericTrace(self.name)

        result = NumericTrace(self.name)
        result.append(*self._points[0])  # First point always retained

        for i in range(1, len(self._points)):
            _, prev_val = self._points[i - 1]
            time, val = self._points[i]
            if val != prev_val:
                result.append(time, val)

        return result

    def copy(self) -> 'NumericTrace':
        """Create a copy of this trace."""
        new_trace = NumericTrace(self.name)
        new_trace._points = self._points.copy()
        return new_trace

    def slice(self, start_time: float, end_time: float) -> 'NumericTrace':
        """
        Get a time-based slice of the trace.

        Args:
            start_time: Start time (inclusive)
            end_time: End time (inclusive)

        Returns:
            New NumericTrace containing points in the time range
        """
        result = NumericTrace(self.name)
        for t, v in self._points:
            if start_time <= t <= end_time:
                result.append(t, v)
        return result

    def __repr__(self) -> str:
        if not self._points:
            return f"NumericTrace('{self.name}', [])"
        elif len(self._points) <= 3:
            pts = ", ".join(f"({t:.2f}, {v})" for t, v in self._points)
            return f"NumericTrace('{self.name}', [{pts}])"
        else:
            first = self._points[0]
            last = self._points[-1]
            return (f"NumericTrace('{self.name}', "
                    f"[({first[0]:.2f}, {first[1]}) ... ({last[0]:.2f}, {last[1]})], "
                    f"len={len(self._points)})")


@dataclass
class NumericObservable:
    """
    Definition of a numeric observable expression.

    Attributes:
        name: Observable name (e.g., "total_busy")
        expression: Expression to evaluate (e.g., "get_S1_busy() + get_S2_busy()")
        model: Model this observable is defined for
    """
    name: str
    expression: str
    model: str


@dataclass
class NumericTraceResult:
    """
    Collection of numeric traces from a model run.

    Attributes:
        model_name: Name of the model
        seed: Random seed used
        traces: Dict mapping observable name -> NumericTrace
    """
    model_name: str
    seed: int
    traces: Dict[str, NumericTrace] = field(default_factory=dict)

    def add_trace(self, trace: NumericTrace) -> None:
        """Add a trace to the result."""
        self.traces[trace.name] = trace

    def get_trace(self, name: str) -> Optional[NumericTrace]:
        """Get trace by observable name."""
        return self.traces.get(name)

    def __repr__(self) -> str:
        trace_names = list(self.traces.keys())
        return f"NumericTraceResult('{self.model_name}', seed={self.seed}, traces={trace_names})"


def numeric_traces_overlap(trace_a: NumericTrace, trace_b: NumericTrace) -> bool:
    """
    Check if two no-stutter numeric traces overlap perfectly.

    Two numeric traces overlap if their no-stutter versions have:
    1. The same sequence of values
    2. The same sequence of transition times

    Args:
        trace_a: First numeric trace
        trace_b: Second numeric trace

    Returns:
        True if no-stutter traces are identical
    """
    ns_a = trace_a.no_stutter_trace()
    ns_b = trace_b.no_stutter_trace()

    if len(ns_a) != len(ns_b):
        return False

    for (t_a, v_a), (t_b, v_b) in zip(ns_a, ns_b):
        # Check values match exactly
        if v_a != v_b:
            return False
        # Check times match (within floating point tolerance)
        if abs(t_a - t_b) > 1e-9:
            return False

    return True


def count_transitions(trace: NumericTrace) -> int:
    """
    Count the number of value transitions in a trace.

    Args:
        trace: Numeric trace to analyze

    Returns:
        Number of times the value changed
    """
    if len(trace) <= 1:
        return 0

    count = 0
    prev_val = trace[0][1]
    for _, val in trace._points[1:]:
        if val != prev_val:
            count += 1
            prev_val = val
    return count
