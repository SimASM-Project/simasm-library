"""
simulation/statistics.py

Statistics collection classes for simulation experiments.

Provides:
- Statistic: Abstract base class for all statistics
- CountStatistic: Counts domain objects created
- TimeAverageStatistic: Time-weighted average of expression
- UtilizationStatistic: Fraction of time condition is true
- DurationStatistic: Duration tracking (cycle time, sojourn time)
- TimeSeriesStatistic: Values sampled at intervals
- ObservationStatistic: Discrete observations (tally statistics)
- StatisticResult: Holds computed statistic results with aggregations

Usage:
    config = StatisticConfig(name="avg_queue", type="time_average", expr="lib.length(queue)")
    stat = TimeAverageStatistic(config)
    
    # During simulation
    stat.update(value=5.0, sim_time=10.0)
    stat.update(value=3.0, sim_time=15.0)
    
    # After simulation
    stat.finalize(end_time=100.0, warmup_time=10.0)
    result = stat.get_result()
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict, Tuple, Union
from math import sqrt

from .config import StatisticConfig, StatisticType, AggregationType


@dataclass
class StatisticResult:
    """
    Holds computed results for a statistic.
    
    Attributes:
        name: Statistic name
        stat_type: Type of statistic
        value: Primary computed value (depends on aggregation type)
        aggregations: Dictionary of all computed aggregations
        observations: Number of observations (for observation-based stats)
        time_span: Total time covered (for time-based stats)
        raw_values: Optional list of raw values (for time_series)
    """
    name: str
    stat_type: StatisticType
    value: Any
    aggregations: Dict[str, Any] = field(default_factory=dict)
    observations: int = 0
    time_span: float = 0.0
    raw_values: Optional[List[Any]] = None
    
    def get_aggregation(self, agg_type: Union[str, AggregationType]) -> Any:
        """Get a specific aggregation value."""
        key = agg_type.value if isinstance(agg_type, AggregationType) else agg_type
        return self.aggregations.get(key)


class Statistic(ABC):
    """
    Abstract base class for all statistics.
    
    Statistics are updated during simulation and produce a result
    after finalization.
    """
    
    def __init__(self, config: StatisticConfig):
        """
        Initialize statistic from configuration.
        
        Args:
            config: Statistic configuration
        """
        self.config = config
        self.name = config.name
        self._finalized = False
        self._result: Optional[StatisticResult] = None
    
    @abstractmethod
    def update(self, value: Any, sim_time: float) -> None:
        """
        Update statistic with a new value.
        
        Args:
            value: Current value (interpretation depends on statistic type)
            sim_time: Current simulation time
        """
        ...
    
    @abstractmethod
    def finalize(self, end_time: float, warmup_time: float = 0.0) -> None:
        """
        Finalize statistic after simulation run.
        
        Computes final values, applying warmup cutoff if specified.
        
        Args:
            end_time: End time of simulation
            warmup_time: Warmup period to exclude (default 0)
        """
        ...
    
    @abstractmethod
    def reset(self) -> None:
        """Reset statistic for a new replication."""
        ...
    
    def get_result(self) -> StatisticResult:
        """
        Get the computed result.
        
        Returns:
            StatisticResult with computed values
        
        Raises:
            RuntimeError: If statistic hasn't been finalized
        """
        if not self._finalized:
            raise RuntimeError(f"Statistic '{self.name}' has not been finalized")
        return self._result
    
    def get_value(self) -> Any:
        """
        Get the primary computed value.
        
        Returns:
            Primary value based on aggregation type
        
        Raises:
            RuntimeError: If statistic hasn't been finalized
        """
        return self.get_result().value
    
    @property
    def is_finalized(self) -> bool:
        """Check if statistic has been finalized."""
        return self._finalized
    
    def _compute_aggregations(self, values: List[float]) -> Dict[str, Any]:
        """
        Compute standard aggregations for a list of values.
        
        Args:
            values: List of numeric values
        
        Returns:
            Dictionary of aggregation name -> value
        """
        if not values:
            return {
                "average": 0.0,
                "min": 0.0,
                "max": 0.0,
                "sum": 0.0,
                "count": 0,
                "std": 0.0,
            }
        
        n = len(values)
        total = sum(values)
        avg = total / n
        min_val = min(values)
        max_val = max(values)
        
        # Compute standard deviation
        if n > 1:
            variance = sum((x - avg) ** 2 for x in values) / (n - 1)
            std = sqrt(variance)
        else:
            std = 0.0
        
        return {
            "average": avg,
            "min": min_val,
            "max": max_val,
            "sum": total,
            "count": n,
            "std": std,
        }
    
    def _get_primary_value(self, aggregations: Dict[str, Any]) -> Any:
        """
        Get primary value based on configured aggregation type.
        
        Args:
            aggregations: Dictionary of computed aggregations
        
        Returns:
            Primary value for the configured aggregation
        """
        agg_type = self.config.aggregation_type
        
        if agg_type == AggregationType.ALL:
            return aggregations.copy()
        else:
            return aggregations.get(agg_type.value, 0.0)


class CountStatistic(Statistic):
    """
    Counts occurrences or domain objects.
    
    Tracks the total count of objects created in a domain.
    Can also count events by incrementing manually.
    Can also read a counter expression from the model.
    """
    
    def __init__(self, config: StatisticConfig):
        super().__init__(config)
        self._counts: List[Tuple[float, int]] = []  # (time, delta)
        self._warmup_count: int = 0
        self._total_count: int = 0
        self._final_value: Optional[int] = None  # For expression-based counts
    
    def update(self, value: Any, sim_time: float) -> None:
        """
        Record a count increment.
        
        Args:
            value: Count to add (typically 1 for object creation)
            sim_time: Current simulation time
        """
        delta = int(value) if value is not None else 1
        self._counts.append((sim_time, delta))
        self._total_count += delta
    
    def finalize(self, end_time: float, warmup_time: float = 0.0) -> None:
        """Finalize count statistic."""
        # If we have a final_value from expression evaluation, use it
        if self._final_value is not None:
            count_value = float(self._final_value)
        else:
            # Compute count after warmup from incremental updates
            count_value = float(sum(
                delta for time, delta in self._counts 
                if time >= warmup_time
            ))
        
        # For count, primary aggregations are based on the single count value
        aggregations = {
            "average": count_value,
            "min": count_value,
            "max": count_value,
            "sum": count_value,
            "count": 1,  # One observation (the total count)
            "std": 0.0,
        }
        
        self._result = StatisticResult(
            name=self.name,
            stat_type=StatisticType.COUNT,
            value=self._get_primary_value(aggregations),
            aggregations=aggregations,
            observations=len(self._counts),
            time_span=end_time - warmup_time,
        )
        self._finalized = True
    
    def reset(self) -> None:
        """Reset for new replication."""
        self._counts.clear()
        self._warmup_count = 0
        self._total_count = 0
        self._finalized = False
        self._result = None
    
    @property
    def current_count(self) -> int:
        """Get current total count (before finalization)."""
        return self._total_count


class TimeAverageStatistic(Statistic):
    """
    Time-weighted average of a numeric expression.
    
    Computes: (1/T) * ∫ value(t) dt over the collection period.
    
    Uses piecewise constant interpolation: value stays constant
    until the next update.
    """
    
    def __init__(self, config: StatisticConfig):
        super().__init__(config)
        self._history: List[Tuple[float, float]] = []  # (time, value)
        self._last_value: float = 0.0
        self._last_time: float = 0.0
        self._initialized: bool = False
    
    def update(self, value: Any, sim_time: float) -> None:
        """
        Record a value change.
        
        Args:
            value: New value of the expression
            sim_time: Current simulation time
        """
        float_value = float(value) if value is not None else 0.0
        self._history.append((sim_time, float_value))
        self._last_value = float_value
        self._last_time = sim_time
        self._initialized = True
    
    def finalize(self, end_time: float, warmup_time: float = 0.0) -> None:
        """Finalize time-average statistic."""
        if not self._history:
            # No data
            aggregations = self._compute_aggregations([])
            self._result = StatisticResult(
                name=self.name,
                stat_type=StatisticType.TIME_AVERAGE,
                value=self._get_primary_value(aggregations),
                aggregations=aggregations,
                observations=0,
                time_span=0.0,
            )
            self._finalized = True
            return
        
        # Compute time-weighted average
        area = 0.0
        collection_start = warmup_time
        collection_end = end_time
        
        # Get value at warmup time (find last value before warmup)
        current_value = 0.0
        for time, value in self._history:
            if time <= warmup_time:
                current_value = value
            else:
                break
        
        # Integrate over collection period
        current_time = collection_start
        
        for time, value in self._history:
            if time <= warmup_time:
                current_value = value
                continue
            
            # Add area for period [current_time, time)
            if time > current_time:
                dt = min(time, collection_end) - current_time
                area += current_value * dt
                current_time = time
            
            current_value = value
            
            if time >= collection_end:
                break
        
        # Add final segment to end_time
        if current_time < collection_end:
            area += current_value * (collection_end - current_time)
        
        # Compute time-weighted average
        time_span = collection_end - collection_start
        if time_span > 0:
            time_avg = area / time_span
        else:
            time_avg = 0.0
        
        # Also collect point values for aggregations
        values_after_warmup = [v for t, v in self._history if t >= warmup_time]
        aggregations = self._compute_aggregations(values_after_warmup)
        
        # Override average with time-weighted average
        aggregations["average"] = time_avg
        aggregations["time_weighted_average"] = time_avg
        
        self._result = StatisticResult(
            name=self.name,
            stat_type=StatisticType.TIME_AVERAGE,
            value=self._get_primary_value(aggregations),
            aggregations=aggregations,
            observations=len(values_after_warmup),
            time_span=time_span,
        )
        self._finalized = True
    
    def reset(self) -> None:
        """Reset for new replication."""
        self._history.clear()
        self._last_value = 0.0
        self._last_time = 0.0
        self._initialized = False
        self._finalized = False
        self._result = None


class UtilizationStatistic(Statistic):
    """
    Fraction of time a boolean condition is true.
    
    Computes: (time condition is true) / (total collection time)
    Result is in [0, 1].
    
    This is a special case of time-average where value is 0 or 1.
    """
    
    def __init__(self, config: StatisticConfig):
        super().__init__(config)
        self._history: List[Tuple[float, bool]] = []  # (time, is_true)
        self._last_state: bool = False
        self._last_time: float = 0.0
    
    def update(self, value: Any, sim_time: float) -> None:
        """
        Record a state change.
        
        Args:
            value: Boolean state (True = utilized/busy)
            sim_time: Current simulation time
        """
        bool_value = bool(value) if value is not None else False
        self._history.append((sim_time, bool_value))
        self._last_state = bool_value
        self._last_time = sim_time
    
    def finalize(self, end_time: float, warmup_time: float = 0.0) -> None:
        """Finalize utilization statistic."""
        if not self._history:
            aggregations = {
                "average": 0.0,
                "min": 0.0,
                "max": 0.0,
                "sum": 0.0,
                "count": 0,
                "std": 0.0,
                "utilization": 0.0,
            }
            self._result = StatisticResult(
                name=self.name,
                stat_type=StatisticType.UTILIZATION,
                value=self._get_primary_value(aggregations),
                aggregations=aggregations,
                observations=0,
                time_span=0.0,
            )
            self._finalized = True
            return
        
        # Compute time spent in true state
        time_true = 0.0
        collection_start = warmup_time
        collection_end = end_time
        
        # Get state at warmup time
        current_state = False
        for time, state in self._history:
            if time <= warmup_time:
                current_state = state
            else:
                break
        
        current_time = collection_start
        
        for time, state in self._history:
            if time <= warmup_time:
                current_state = state
                continue
            
            # Add time for period [current_time, time)
            if time > current_time and current_state:
                dt = min(time, collection_end) - current_time
                time_true += dt
            
            current_time = time
            current_state = state
            
            if time >= collection_end:
                break
        
        # Add final segment to end_time
        if current_time < collection_end and current_state:
            time_true += collection_end - current_time
        
        # Compute utilization
        time_span = collection_end - collection_start
        if time_span > 0:
            utilization = time_true / time_span
        else:
            utilization = 0.0
        
        aggregations = {
            "average": utilization,
            "min": utilization,
            "max": utilization,
            "sum": time_true,
            "count": len([s for t, s in self._history if t >= warmup_time]),
            "std": 0.0,
            "utilization": utilization,
            "time_true": time_true,
            "time_false": time_span - time_true,
        }
        
        self._result = StatisticResult(
            name=self.name,
            stat_type=StatisticType.UTILIZATION,
            value=self._get_primary_value(aggregations),
            aggregations=aggregations,
            observations=len(self._history),
            time_span=time_span,
        )
        self._finalized = True
    
    def reset(self) -> None:
        """Reset for new replication."""
        self._history.clear()
        self._last_state = False
        self._last_time = 0.0
        self._finalized = False
        self._result = None


class DurationStatistic(Statistic):
    """
    Tracks durations (cycle times, sojourn times, etc.).
    
    Can be used in two modes:
    1. Simple: Record duration values directly
    2. Lifecycle: Track start/end times for entities
    """
    
    def __init__(self, config: StatisticConfig):
        super().__init__(config)
        self._durations: List[Tuple[float, float]] = []  # (end_time, duration)
        # For lifecycle tracking
        self._active_entities: Dict[Any, float] = {}  # entity_id -> start_time
    
    def update(self, value: Any, sim_time: float) -> None:
        """
        Record a duration observation.
        
        Args:
            value: Duration value
            sim_time: Time when duration was observed (typically end time)
        """
        duration = float(value) if value is not None else 0.0
        self._durations.append((sim_time, duration))
    
    def start_entity(self, entity_id: Any, sim_time: float) -> None:
        """
        Start tracking duration for an entity.
        
        Args:
            entity_id: Unique identifier for the entity
            sim_time: Start time
        """
        self._active_entities[entity_id] = sim_time
    
    def end_entity(self, entity_id: Any, sim_time: float) -> None:
        """
        End tracking for an entity and record its duration.
        
        Args:
            entity_id: Unique identifier for the entity
            sim_time: End time
        """
        if entity_id in self._active_entities:
            start_time = self._active_entities.pop(entity_id)
            duration = sim_time - start_time
            self._durations.append((sim_time, duration))
    
    def finalize(self, end_time: float, warmup_time: float = 0.0) -> None:
        """Finalize duration statistic."""
        # Filter durations completed after warmup
        durations_after_warmup = [
            d for t, d in self._durations 
            if t >= warmup_time
        ]
        
        aggregations = self._compute_aggregations(durations_after_warmup)
        
        self._result = StatisticResult(
            name=self.name,
            stat_type=StatisticType.DURATION,
            value=self._get_primary_value(aggregations),
            aggregations=aggregations,
            observations=len(durations_after_warmup),
            time_span=end_time - warmup_time,
            raw_values=durations_after_warmup if self.config.aggregation == "all" else None,
        )
        self._finalized = True
    
    def reset(self) -> None:
        """Reset for new replication."""
        self._durations.clear()
        self._active_entities.clear()
        self._finalized = False
        self._result = None
    
    @property
    def active_count(self) -> int:
        """Number of entities currently being tracked."""
        return len(self._active_entities)


class TimeSeriesStatistic(Statistic):
    """
    Records expression values at regular intervals.
    
    Samples the value at fixed intervals for plotting or analysis.
    Uses piecewise constant interpolation - value stays constant
    until the next update.
    """
    
    def __init__(self, config: StatisticConfig):
        super().__init__(config)
        self._series: List[Tuple[float, Any]] = []  # (time, value)
        self._current_value: Any = None
        self._interval = config.interval or 1.0
        self._next_sample_time: float = 0.0
    
    def update(self, value: Any, sim_time: float) -> None:
        """
        Update current value and sample if at interval.
        
        Args:
            value: Current value
            sim_time: Current simulation time
        """
        # First, catch up on any missed samples using the OLD value
        while sim_time >= self._next_sample_time:
            # Use current (old) value for samples before this update
            sample_value = self._current_value if self._current_value is not None else value
            self._series.append((self._next_sample_time, sample_value))
            self._next_sample_time += self._interval
        
        # Now update to the new value
        self._current_value = value
    
    def sample_at(self, sim_time: float) -> None:
        """
        Force a sample at specific time.
        
        Args:
            sim_time: Time to sample at
        """
        if self._current_value is not None:
            self._series.append((sim_time, self._current_value))
    
    def finalize(self, end_time: float, warmup_time: float = 0.0) -> None:
        """Finalize time series statistic."""
        # Filter series after warmup
        series_after_warmup = [
            (t, v) for t, v in self._series 
            if t >= warmup_time
        ]
        
        # Extract numeric values for aggregations
        numeric_values = []
        for t, v in series_after_warmup:
            try:
                numeric_values.append(float(v))
            except (TypeError, ValueError):
                pass
        
        aggregations = self._compute_aggregations(numeric_values)
        
        self._result = StatisticResult(
            name=self.name,
            stat_type=StatisticType.TIME_SERIES,
            value=series_after_warmup,  # Time series returns the series itself
            aggregations=aggregations,
            observations=len(series_after_warmup),
            time_span=end_time - warmup_time,
            raw_values=series_after_warmup,
        )
        self._finalized = True
    
    def reset(self) -> None:
        """Reset for new replication."""
        self._series.clear()
        self._current_value = None
        self._next_sample_time = 0.0
        self._finalized = False
        self._result = None
    
    @property
    def series(self) -> List[Tuple[float, Any]]:
        """Get current series (before finalization)."""
        return list(self._series)


class ObservationStatistic(Statistic):
    """
    Collects discrete observations (tally statistics).
    
    Records individual observations and computes standard
    statistical aggregations.
    """
    
    def __init__(self, config: StatisticConfig):
        super().__init__(config)
        self._observations: List[Tuple[float, float]] = []  # (time, value)
    
    def update(self, value: Any, sim_time: float) -> None:
        """
        Record an observation.
        
        Args:
            value: Observed value
            sim_time: Time of observation
        """
        float_value = float(value) if value is not None else 0.0
        self._observations.append((sim_time, float_value))
    
    def finalize(self, end_time: float, warmup_time: float = 0.0) -> None:
        """Finalize observation statistic."""
        # Filter observations after warmup
        values_after_warmup = [
            v for t, v in self._observations 
            if t >= warmup_time
        ]
        
        aggregations = self._compute_aggregations(values_after_warmup)
        
        self._result = StatisticResult(
            name=self.name,
            stat_type=StatisticType.OBSERVATION,
            value=self._get_primary_value(aggregations),
            aggregations=aggregations,
            observations=len(values_after_warmup),
            time_span=end_time - warmup_time,
            raw_values=values_after_warmup if self.config.aggregation == "all" else None,
        )
        self._finalized = True
    
    def reset(self) -> None:
        """Reset for new replication."""
        self._observations.clear()
        self._finalized = False
        self._result = None
    
    @property
    def observation_count(self) -> int:
        """Get current observation count (before finalization)."""
        return len(self._observations)


def create_statistic(config: StatisticConfig) -> Statistic:
    """
    Factory function to create appropriate statistic from config.
    
    Args:
        config: Statistic configuration
    
    Returns:
        Appropriate Statistic subclass instance
    
    Raises:
        ValueError: If statistic type is unknown
    """
    stat_type = config.statistic_type
    
    if stat_type == StatisticType.COUNT:
        return CountStatistic(config)
    elif stat_type == StatisticType.TIME_AVERAGE:
        return TimeAverageStatistic(config)
    elif stat_type == StatisticType.UTILIZATION:
        return UtilizationStatistic(config)
    elif stat_type == StatisticType.DURATION:
        return DurationStatistic(config)
    elif stat_type == StatisticType.TIME_SERIES:
        return TimeSeriesStatistic(config)
    elif stat_type == StatisticType.OBSERVATION:
        return ObservationStatistic(config)
    else:
        raise ValueError(f"Unknown statistic type: {stat_type}")
