"""
simulation/runner.py

Experiment runner for multiple replications.

Provides:
- ReplicationResult: Result from single replication
- SummaryStatistics: Aggregated stats across replications
- ExperimentResult: Complete experiment results
- ExperimentRunner: Runs replications and aggregates results

Usage:
    config = ExperimentConfig(
        model_source=model_code,
        replications=ReplicationSettings(count=30, warmup=100.0, length=1000.0),
        statistics=[
            StatisticConfig(name="avg_queue", type="time_average", expr="queue_length"),
            StatisticConfig(name="util", type="utilization", expr="server_busy"),
        ]
    )
    
    runner = ExperimentRunner(config)
    result = runner.run()
    
    print(f"Mean queue length: {result.summary['avg_queue'].mean}")
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Protocol, Tuple
from math import sqrt
import statistics as pystats
from abc import ABC, abstractmethod

from simasm.log.logger import get_logger

from .config import ExperimentConfig, StatisticConfig, ReplicationSettings
from .statistics import StatisticResult
from .collector import StatisticsCollector

logger = get_logger(__name__)


# ============================================================================
# Result Classes
# ============================================================================

@dataclass
class ReplicationResult:
    """
    Result from a single replication.

    Attributes:
        replication_id: 1-indexed replication number
        seed: Random seed used for this replication
        statistics: Dictionary of statistic name -> value
        traces: Dictionary of statistic name -> [(time, value), ...] for traced statistics
        final_time: Simulation time at end of replication
        steps_taken: Number of simulation steps executed
        wall_time: Wall clock time for this replication (seconds)
    """
    replication_id: int
    seed: int
    statistics: Dict[str, Any]
    traces: Dict[str, List[Tuple[float, Any]]] = field(default_factory=dict)
    final_time: float = 0.0
    steps_taken: int = 0
    wall_time: float = 0.0

    def get_statistic(self, name: str) -> Any:
        """Get value for a specific statistic."""
        return self.statistics.get(name)

    def get_trace(self, name: str) -> Optional[List[Tuple[float, Any]]]:
        """Get trace data for a statistic."""
        return self.traces.get(name)


@dataclass
class SummaryStatistics:
    """
    Summary statistics for a metric across replications.
    
    Attributes:
        mean: Mean value across replications
        std_dev: Sample standard deviation
        min_val: Minimum value
        max_val: Maximum value
        ci_lower: Lower bound of 95% confidence interval
        ci_upper: Upper bound of 95% confidence interval
        n: Number of observations
    """
    mean: float
    std_dev: float
    min_val: float
    max_val: float
    ci_lower: float
    ci_upper: float
    n: int = 0
    
    @property
    def ci_width(self) -> float:
        """Width of confidence interval."""
        return self.ci_upper - self.ci_lower
    
    @property
    def relative_error(self) -> float:
        """Relative half-width of CI (as fraction of mean)."""
        if self.mean == 0:
            return 0.0
        return (self.ci_upper - self.mean) / abs(self.mean)


@dataclass
class ExperimentResult:
    """
    Result from a complete experiment (all replications).
    
    Attributes:
        config: Experiment configuration used
        replications: List of individual replication results
        summary: Summary statistics per metric
        total_wall_time: Total wall clock time for experiment
    """
    config: ExperimentConfig
    replications: List[ReplicationResult]
    summary: Dict[str, SummaryStatistics]
    total_wall_time: float = 0.0
    
    def get_replication(self, rep_id: int) -> Optional[ReplicationResult]:
        """Get result for specific replication (1-indexed)."""
        for rep in self.replications:
            if rep.replication_id == rep_id:
                return rep
        return None
    
    def get_summary(self, stat_name: str) -> Optional[SummaryStatistics]:
        """Get summary statistics for a specific statistic."""
        return self.summary.get(stat_name)
    
    def get_values(self, stat_name: str) -> List[Any]:
        """Get all values for a statistic across replications."""
        return [r.get_statistic(stat_name) for r in self.replications]
    
    @property
    def num_replications(self) -> int:
        """Number of replications completed."""
        return len(self.replications)
    
    @property
    def statistic_names(self) -> List[str]:
        """Names of all statistics."""
        if self.replications:
            return list(self.replications[0].statistics.keys())
        return []


# ============================================================================
# Simulation Model Protocol
# ============================================================================

class SimulationModel(Protocol):
    """
    Protocol for simulation models that can be run by ExperimentRunner.
    
    Models must implement this interface to be compatible with the runner.
    """
    
    def reset(self, seed: Optional[int] = None) -> None:
        """Reset model for a new replication."""
        ...
    
    def step(self) -> bool:
        """Execute one step. Returns False if simulation should stop."""
        ...
    
    @property
    def sim_time(self) -> float:
        """Current simulation time."""
        ...
    
    @property
    def step_count(self) -> int:
        """Number of steps executed."""
        ...


# ============================================================================
# Experiment Runner
# ============================================================================

class ExperimentRunner:
    """
    Runs simulation experiments with multiple replications.
    
    Supports two modes:
    1. With a SimulationModel instance (programmatic models)
    2. With model source/path (parsed SimASM models) - future
    
    Usage:
        # With programmatic model
        runner = ExperimentRunner(config)
        runner.set_model(my_model)
        result = runner.run()
        
        # With callbacks for custom statistics collection
        runner = ExperimentRunner(config)
        runner.set_model(my_model)
        result = runner.run(
            on_step=lambda state, time: collector.on_step(state, time),
            on_replication_end=lambda rep_id: print(f"Rep {rep_id} done")
        )
    """
    
    # T-values for 95% CI by degrees of freedom (df = n-1)
    # For df >= 30, use 1.96 (z-value approximation)
    T_VALUES = {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
        6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045,
    }
    
    def __init__(self, config: ExperimentConfig):
        """
        Create experiment runner.
        
        Args:
            config: Experiment configuration
        """
        self.config = config
        self._model: Optional[SimulationModel] = None
        self._collector: Optional[StatisticsCollector] = None
    
    def set_model(self, model: SimulationModel) -> None:
        """
        Set the simulation model to run.
        
        Args:
            model: Model implementing SimulationModel protocol
        """
        self._model = model
    
    def set_collector(self, collector: StatisticsCollector) -> None:
        """
        Set custom statistics collector.
        
        Args:
            collector: Pre-configured StatisticsCollector
        """
        self._collector = collector
    
    def run(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        on_step: Optional[Callable[[Any, float], None]] = None,
        on_replication_start: Optional[Callable[[int, int], None]] = None,
        on_replication_end: Optional[Callable[[int, ReplicationResult], None]] = None,
    ) -> ExperimentResult:
        """
        Run all replications and aggregate results.
        
        Args:
            progress_callback: Called with (current_rep, total_reps)
            on_step: Called after each simulation step with (state, sim_time)
            on_replication_start: Called at start of replication with (rep_id, seed)
            on_replication_end: Called at end of replication with (rep_id, result)
        
        Returns:
            ExperimentResult with all replication results and summary
        
        Raises:
            RuntimeError: If no model is set
        """
        if self._model is None:
            raise RuntimeError("No model set. Call set_model() first.")
        
        import time
        start_wall_time = time.time()
        
        results: List[ReplicationResult] = []
        settings = self.config.replications
        
        for i in range(settings.count):
            rep_id = i + 1
            seed = settings.seed_for_replication(i)
            
            if progress_callback:
                progress_callback(rep_id, settings.count)
            
            if on_replication_start:
                on_replication_start(rep_id, seed)
            
            result = self._run_replication(
                rep_id=rep_id,
                seed=seed,
                on_step=on_step,
            )
            results.append(result)
            
            if on_replication_end:
                on_replication_end(rep_id, result)
        
        total_wall_time = time.time() - start_wall_time
        
        # Aggregate results
        summary = self._aggregate_results(results)
        
        return ExperimentResult(
            config=self.config,
            replications=results,
            summary=summary,
            total_wall_time=total_wall_time,
        )
    
    def _run_replication(
        self,
        rep_id: int,
        seed: int,
        on_step: Optional[Callable[[Any, float], None]] = None,
    ) -> ReplicationResult:
        """
        Run a single replication.
        
        Args:
            rep_id: Replication ID (1-indexed)
            seed: Random seed
            on_step: Optional step callback
        
        Returns:
            ReplicationResult for this replication
        """
        import time
        start_time = time.time()
        
        settings = self.config.replications
        
        # Reset model
        self._model.reset(seed=seed)
        
        # Reset collector if we have one
        if self._collector:
            self._collector.reset()
        
        # Run until end time
        end_time = settings.length
        
        while self._model.sim_time < end_time:
            if not self._model.step():
                break  # Model indicates stop
            
            if on_step:
                on_step(None, self._model.sim_time)
        
        # Finalize collector if we have one
        statistics: Dict[str, Any] = {}
        if self._collector:
            self._collector.finalize(end_time, settings.warmup)
            for name, result in self._collector.get_results().items():
                statistics[name] = result.value
        
        wall_time = time.time() - start_time
        
        logger.debug(
            f"Replication {rep_id}: seed={seed}, steps={self._model.step_count}, "
            f"time={self._model.sim_time:.2f}, wall={wall_time:.2f}s"
        )
        
        return ReplicationResult(
            replication_id=rep_id,
            seed=seed,
            statistics=statistics,
            final_time=self._model.sim_time,
            steps_taken=self._model.step_count,
            wall_time=wall_time,
        )
    
    def _aggregate_results(
        self, 
        results: List[ReplicationResult]
    ) -> Dict[str, SummaryStatistics]:
        """
        Compute summary statistics across replications.
        
        Args:
            results: List of replication results
        
        Returns:
            Dictionary of statistic name -> SummaryStatistics
        """
        if not results:
            return {}
        
        summary: Dict[str, SummaryStatistics] = {}
        
        # Get all statistic names from first replication
        stat_names = list(results[0].statistics.keys())
        
        for name in stat_names:
            values = [r.statistics.get(name) for r in results]
            
            # Filter to numeric values only
            numeric_values = []
            for v in values:
                if isinstance(v, (int, float)) and v is not None:
                    numeric_values.append(float(v))
            
            if numeric_values:
                summary[name] = self._compute_summary(numeric_values)
        
        return summary
    
    def _compute_summary(self, values: List[float]) -> SummaryStatistics:
        """
        Compute summary statistics for a list of values.
        
        Args:
            values: List of numeric values
        
        Returns:
            SummaryStatistics with mean, std, CI, etc.
        """
        n = len(values)
        
        if n == 0:
            return SummaryStatistics(
                mean=0.0, std_dev=0.0, min_val=0.0, max_val=0.0,
                ci_lower=0.0, ci_upper=0.0, n=0
            )
        
        mean = pystats.mean(values)
        min_val = min(values)
        max_val = max(values)
        
        if n > 1:
            std = pystats.stdev(values)
            
            # Get t-value for 95% CI
            df = n - 1
            if df >= 30:
                t_value = 1.96  # Use z-value for large samples
            else:
                t_value = self.T_VALUES.get(df, 2.0)
            
            # Compute confidence interval
            margin = t_value * std / sqrt(n)
            ci_lower = mean - margin
            ci_upper = mean + margin
        else:
            std = 0.0
            ci_lower = mean
            ci_upper = mean
        
        return SummaryStatistics(
            mean=mean,
            std_dev=std,
            min_val=min_val,
            max_val=max_val,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            n=n,
        )
    
    def _get_t_value(self, df: int) -> float:
        """
        Get t-value for 95% confidence interval.
        
        Args:
            df: Degrees of freedom (n-1)
        
        Returns:
            t-value for 95% CI
        """
        if df >= 30:
            return 1.96
        return self.T_VALUES.get(df, 2.0)


# ============================================================================
# Simple Model Runner (for models without full SimulationModel protocol)
# ============================================================================

class SimpleModelRunner:
    """
    Simplified runner for models with run() method.
    
    For models that don't implement the full SimulationModel protocol
    but have a simpler interface.
    
    Usage:
        runner = SimpleModelRunner()
        result = runner.run_experiment(
            model=my_model,
            n_replications=30,
            end_time=1000.0,
            warmup_time=100.0,
            base_seed=42,
            get_statistics=lambda model: {"util": model.utilization},
        )
    """
    
    def __init__(self):
        """Create simple model runner."""
        self._t_values = ExperimentRunner.T_VALUES
    
    def run_experiment(
        self,
        model: Any,
        n_replications: int,
        end_time: float,
        warmup_time: float = 0.0,
        base_seed: int = 42,
        get_statistics: Optional[Callable[[Any], Dict[str, Any]]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> ExperimentResult:
        """
        Run experiment with simple model interface.
        
        Args:
            model: Model with reset(seed) and run(end_time) methods
            n_replications: Number of replications
            end_time: Simulation end time
            warmup_time: Warmup period
            base_seed: Base random seed
            get_statistics: Function to extract statistics from model
            progress_callback: Progress callback (rep_id, total)
        
        Returns:
            ExperimentResult
        """
        import time
        start_wall_time = time.time()
        
        results: List[ReplicationResult] = []
        
        for i in range(n_replications):
            rep_id = i + 1
            seed = base_seed + i
            
            if progress_callback:
                progress_callback(rep_id, n_replications)
            
            rep_start = time.time()
            
            # Reset and run
            model.reset(seed=seed)
            model.run(end_time=end_time)
            
            # Extract statistics
            statistics = {}
            if get_statistics:
                statistics = get_statistics(model)
            
            # Get model info if available
            final_time = getattr(model, 'sim_time', end_time)
            if callable(final_time):
                final_time = final_time()
            
            step_count = getattr(model, 'step_count', 0)
            if callable(step_count):
                step_count = step_count()
            
            wall_time = time.time() - rep_start
            
            results.append(ReplicationResult(
                replication_id=rep_id,
                seed=seed,
                statistics=statistics,
                final_time=float(final_time),
                steps_taken=int(step_count),
                wall_time=wall_time,
            ))
        
        total_wall_time = time.time() - start_wall_time
        
        # Create minimal config
        config = ExperimentConfig(
            model_source="<simple model>",
            replications=ReplicationSettings(
                count=n_replications,
                warmup=warmup_time,
                length=end_time,
                base_seed=base_seed,
            ),
        )
        
        # Aggregate
        summary = self._aggregate_results(results)
        
        return ExperimentResult(
            config=config,
            replications=results,
            summary=summary,
            total_wall_time=total_wall_time,
        )
    
    def _aggregate_results(
        self, 
        results: List[ReplicationResult]
    ) -> Dict[str, SummaryStatistics]:
        """Aggregate results across replications."""
        if not results:
            return {}
        
        summary: Dict[str, SummaryStatistics] = {}
        stat_names = list(results[0].statistics.keys())
        
        for name in stat_names:
            values = []
            for r in results:
                v = r.statistics.get(name)
                if isinstance(v, (int, float)) and v is not None:
                    values.append(float(v))
            
            if values:
                summary[name] = self._compute_summary(values)
        
        return summary
    
    def _compute_summary(self, values: List[float]) -> SummaryStatistics:
        """Compute summary statistics."""
        n = len(values)
        
        if n == 0:
            return SummaryStatistics(
                mean=0.0, std_dev=0.0, min_val=0.0, max_val=0.0,
                ci_lower=0.0, ci_upper=0.0, n=0
            )
        
        mean = pystats.mean(values)
        min_val = min(values)
        max_val = max(values)
        
        if n > 1:
            std = pystats.stdev(values)
            df = n - 1
            t_value = self._t_values.get(df, 1.96) if df < 30 else 1.96
            margin = t_value * std / sqrt(n)
            ci_lower = mean - margin
            ci_upper = mean + margin
        else:
            std = 0.0
            ci_lower = mean
            ci_upper = mean
        
        return SummaryStatistics(
            mean=mean,
            std_dev=std,
            min_val=min_val,
            max_val=max_val,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            n=n,
        )


# ============================================================================
# Convenience Functions
# ============================================================================

def run_replications(
    model: Any,
    n_replications: int,
    end_time: float,
    warmup_time: float = 0.0,
    base_seed: int = 42,
    get_statistics: Optional[Callable[[Any], Dict[str, Any]]] = None,
) -> ExperimentResult:
    """
    Convenience function to run multiple replications.
    
    Args:
        model: Model with reset(seed) and run(end_time) methods
        n_replications: Number of replications
        end_time: Simulation end time
        warmup_time: Warmup period
        base_seed: Base random seed
        get_statistics: Function to extract statistics from model
    
    Returns:
        ExperimentResult with all results
    
    Example:
        result = run_replications(
            model=MM1Model(arrival_rate=0.8, service_rate=1.0),
            n_replications=30,
            end_time=1000.0,
            warmup_time=100.0,
            get_statistics=lambda m: {
                "utilization": m.utilization,
                "avg_queue": m.avg_queue_length,
            }
        )
        print(f"Utilization: {result.summary['utilization'].mean:.3f}")
    """
    runner = SimpleModelRunner()
    return runner.run_experiment(
        model=model,
        n_replications=n_replications,
        end_time=end_time,
        warmup_time=warmup_time,
        base_seed=base_seed,
        get_statistics=get_statistics,
    )
