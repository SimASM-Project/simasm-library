"""
simulation/config.py

Configuration classes for simulation experiments.

Provides:
- StatisticConfig: Configuration for a single statistic
- ReplicationSettings: Settings for replications
- ExperimentConfig: Complete experiment configuration

Usage:
    config = ExperimentConfig(
        model_path="models/mm1.simasm",
        replications=ReplicationSettings(count=30, warmup=100.0, length=1000.0),
        statistics=[
            StatisticConfig(name="avg_queue", type="time_average", expr="lib.length(queue)"),
            StatisticConfig(name="utilization", type="utilization", expr="server_status == Busy"),
        ]
    )
"""

from dataclasses import dataclass, field
from typing import Optional, List, Any
from enum import Enum


class StatisticType(Enum):
    """Types of statistics that can be collected."""
    COUNT = "count"                  # Count of domain objects or events
    TIME_AVERAGE = "time_average"    # Time-weighted average of expression
    UTILIZATION = "utilization"      # Fraction of time condition is true
    DURATION = "duration"            # Duration tracking (cycle time, sojourn time)
    TIME_SERIES = "time_series"      # Values sampled at intervals
    OBSERVATION = "observation"      # Discrete observations (tally statistics)


class AggregationType(Enum):
    """How to aggregate statistic values across observations or replications."""
    AVERAGE = "average"    # Mean value
    MIN = "min"            # Minimum value
    MAX = "max"            # Maximum value
    SUM = "sum"            # Sum of values
    COUNT = "count"        # Count of observations
    STD = "std"            # Standard deviation
    ALL = "all"            # Report all aggregations (avg, min, max, std, count)


class ConfigError(Exception):
    """Raised when configuration is invalid."""
    pass


@dataclass
class StatisticConfig:
    """
    Configuration for a single statistic.

    Attributes:
        name: Unique identifier for this statistic
        type: Type of statistic (count, time_average, utilization, duration, time_series, observation)
        domain: Domain name for count statistics (e.g., "Customer")
        expr: Expression string for time_average/utilization/time_series/observation
        interval: Sampling interval for time_series statistics
        condition: Optional filter condition
        aggregation: How to aggregate values (average, min, max, sum, count, std, all)
        start_expr: Expression that triggers duration start (for duration statistics)
        end_expr: Expression that triggers duration end (for duration statistics)
        entity_domain: Domain of entities being tracked (for duration statistics)
        trace: Whether to capture time series trace for this statistic (for plotting)
    """
    name: str
    type: str  # "count", "time_average", "utilization", "duration", "time_series", "observation"
    domain: Optional[str] = None
    expr: Optional[str] = None
    interval: Optional[float] = None
    condition: Optional[str] = None
    aggregation: str = "average"  # "average", "min", "max", "sum", "count", "std", "all"
    start_expr: Optional[str] = None
    end_expr: Optional[str] = None
    entity_domain: Optional[str] = None
    trace: bool = False
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate()
    
    def _validate(self) -> None:
        """Validate that configuration is consistent."""
        # Validate type
        valid_types = {t.value for t in StatisticType}
        if self.type not in valid_types:
            raise ConfigError(
                f"Invalid statistic type '{self.type}'. "
                f"Must be one of: {', '.join(sorted(valid_types))}"
            )
        
        # Validate name
        if not self.name or not self.name.strip():
            raise ConfigError("Statistic name cannot be empty")
        
        # Validate aggregation
        valid_aggregations = {a.value for a in AggregationType}
        if self.aggregation not in valid_aggregations:
            raise ConfigError(
                f"Invalid aggregation '{self.aggregation}'. "
                f"Must be one of: {', '.join(sorted(valid_aggregations))}"
            )
        
        # Type-specific validation
        if self.type == StatisticType.COUNT.value:
            if not self.domain and not self.expr:
                raise ConfigError(
                    f"Statistic '{self.name}' of type 'count' requires 'domain' or 'expr'"
                )
        elif self.type in (StatisticType.TIME_AVERAGE.value, 
                           StatisticType.UTILIZATION.value,
                           StatisticType.OBSERVATION.value):
            if not self.expr:
                raise ConfigError(
                    f"Statistic '{self.name}' of type '{self.type}' requires 'expr'"
                )
        elif self.type == StatisticType.TIME_SERIES.value:
            if not self.expr:
                raise ConfigError(
                    f"Statistic '{self.name}' of type 'time_series' requires 'expr'"
                )
            if self.interval is not None and self.interval <= 0:
                raise ConfigError(
                    f"Statistic '{self.name}' interval must be positive"
                )
        elif self.type == StatisticType.DURATION.value:
            # Check partial lifecycle specification first (more specific errors)
            if self.start_expr and not self.end_expr:
                raise ConfigError(
                    f"Statistic '{self.name}' has 'start_expr' but missing 'end_expr'"
                )
            if self.end_expr and not self.start_expr:
                raise ConfigError(
                    f"Statistic '{self.name}' has 'end_expr' but missing 'start_expr'"
                )
            # Duration requires either expr (simple) or start_expr/end_expr (lifecycle)
            if not self.expr and not (self.start_expr and self.end_expr):
                raise ConfigError(
                    f"Statistic '{self.name}' of type 'duration' requires either 'expr' "
                    f"or both 'start_expr' and 'end_expr'"
                )
    
    @property
    def statistic_type(self) -> StatisticType:
        """Return the StatisticType enum value."""
        return StatisticType(self.type)
    
    @property
    def aggregation_type(self) -> AggregationType:
        """Return the AggregationType enum value."""
        return AggregationType(self.aggregation)
    
    @property
    def is_lifecycle_duration(self) -> bool:
        """Check if this is a lifecycle-based duration statistic."""
        return self.type == StatisticType.DURATION.value and self.start_expr is not None


@dataclass
class ReplicationSettings:
    """
    Settings for simulation replications.

    Attributes:
        count: Number of replications to run
        warmup: Warm-up period (time units) before collecting statistics
        length: Total run length per replication (time units)
        base_seed: Starting seed for random number generation
        generate_plots: Whether to automatically generate plots after experiment
        trace_interval: Time interval for sampling traced statistics
    """
    count: int = 30
    warmup: float = 0.0
    length: float = 1000.0
    base_seed: int = 42
    generate_plots: bool = False
    trace_interval: float = 1.0
    
    def __post_init__(self):
        """Validate settings after initialization."""
        self._validate()
    
    def _validate(self) -> None:
        """Validate replication settings."""
        if self.count < 1:
            raise ConfigError(f"Replication count must be >= 1, got {self.count}")
        
        if self.warmup < 0:
            raise ConfigError(f"Warmup must be >= 0, got {self.warmup}")
        
        if self.length <= 0:
            raise ConfigError(f"Run length must be > 0, got {self.length}")
        
        if self.warmup >= self.length:
            raise ConfigError(
                f"Warmup ({self.warmup}) must be less than length ({self.length})"
            )
    
    def seed_for_replication(self, replication_id: int) -> int:
        """
        Get the seed for a specific replication.
        
        Args:
            replication_id: Replication number (0-indexed)
        
        Returns:
            Seed for this replication
        """
        return self.base_seed + replication_id


@dataclass
class ExperimentConfig:
    """
    Complete configuration for a simulation experiment.
    
    Attributes:
        name: Experiment name/description
        model_path: Path to .simasm model file
        model_source: Inline model source code (alternative to model_path)
        replications: Replication settings
        statistics: List of statistics to collect
        output_format: Output format ("json", "csv")
        output_path: Path for output file (None = no file output)
        time_var: Name of simulation time variable
        fel_var: Name of Future Event List variable
    """
    name: Optional[str] = None
    model_path: Optional[str] = None
    model_source: Optional[str] = None
    replications: ReplicationSettings = field(default_factory=ReplicationSettings)
    statistics: List[StatisticConfig] = field(default_factory=list)
    output_format: str = "json"
    output_path: Optional[str] = None
    time_var: str = "sim_clocktime"
    fel_var: str = "FEL"
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate()
    
    def _validate(self) -> None:
        """Validate experiment configuration."""
        # Must have either model_path or model_source
        if not self.model_path and not self.model_source:
            raise ConfigError(
                "Must provide either 'model_path' or 'model_source'"
            )
        
        if self.model_path and self.model_source:
            raise ConfigError(
                "Cannot provide both 'model_path' and 'model_source'"
            )
        
        # Validate output format
        valid_formats = {"json", "csv"}
        if self.output_format not in valid_formats:
            raise ConfigError(
                f"Invalid output format '{self.output_format}'. "
                f"Must be one of: {', '.join(valid_formats)}"
            )
        
        # Check for duplicate statistic names
        names = [s.name for s in self.statistics]
        if len(names) != len(set(names)):
            duplicates = [n for n in names if names.count(n) > 1]
            raise ConfigError(
                f"Duplicate statistic names: {set(duplicates)}"
            )
    
    def add_statistic(self, stat_config: StatisticConfig) -> None:
        """
        Add a statistic configuration.
        
        Args:
            stat_config: Statistic configuration to add
        
        Raises:
            ConfigError: If name already exists
        """
        if any(s.name == stat_config.name for s in self.statistics):
            raise ConfigError(
                f"Statistic with name '{stat_config.name}' already exists"
            )
        self.statistics.append(stat_config)
    
    def get_statistic(self, name: str) -> Optional[StatisticConfig]:
        """
        Get a statistic configuration by name.
        
        Args:
            name: Statistic name
        
        Returns:
            StatisticConfig if found, None otherwise
        """
        for stat in self.statistics:
            if stat.name == name:
                return stat
        return None
    
    @property
    def has_warmup(self) -> bool:
        """Check if experiment has a warmup period."""
        return self.replications.warmup > 0
    
    @property
    def total_time(self) -> float:
        """Total simulation time per replication."""
        return self.replications.length
    
    @property
    def collection_time(self) -> float:
        """Time during which statistics are collected."""
        return self.replications.length - self.replications.warmup
