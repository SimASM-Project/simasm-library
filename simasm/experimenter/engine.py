"""
experimenter/engine.py

Engine that executes experiment, verification, and analysis specifications.

Provides:
- SimASMModel: Adapter that wraps LoadedProgram as SimulationModel
- ExperimenterEngine: Orchestrates experiment execution
- VerificationEngine: Orchestrates verification execution
- AnalysisEngine: Orchestrates complexity analysis execution
- run_experiment: Convenience function
- run_verification: Convenience function
- run_analysis: Convenience function

Usage:
    from simasm.experimenter import run_experiment

    result = run_experiment("experiments/mmn.simasm")
    print(result.summary)
"""

from pathlib import Path
from typing import Optional, Union, Dict, Any, List
import time

from simasm.log.logger import get_logger

from simasm.parser import load_file, LoadedProgram
from simasm.runtime.stepper import ASMStepper, StepperConfig

from simasm.simulation.config import (
    ExperimentConfig, 
    ReplicationSettings, 
    StatisticConfig,
)
from simasm.simulation.runner import (
    ExperimentRunner,
    ExperimentResult,
    ReplicationResult,
    SummaryStatistics,
    SimulationModel,
)
from simasm.simulation.output import write_results
from simasm.simulation.collector import StatisticsCollector

from .ast import ExperimentNode, StatisticNode, ReplicationNode, ExperimentOutputNode
from .transformer import ExperimentParser

logger = get_logger(__name__)


class SimASMModel:
    """
    Adapter that wraps a LoadedProgram to implement SimulationModel protocol.
    
    This allows SimASM programs to be run by ExperimentRunner.
    
    Usage:
        loaded = load_file("model.simasm", seed=42)
        model = SimASMModel(loaded)
        model.run(end_time=1000.0)
        print(f"Final time: {model.sim_time}")
    """
    
    def __init__(
        self,
        model_path: str,
        time_var: str = "sim_clocktime",
    ):
        """
        Create SimASMModel adapter.
        
        Args:
            model_path: Path to .simasm model file
            time_var: Name of simulation time variable in model
        """
        self._model_path = model_path
        self._time_var = time_var
        self._loaded: Optional[LoadedProgram] = None
        self._stepper: Optional[ASMStepper] = None
        self._current_seed: int = 42
    
    def reset(self, seed: Optional[int] = None) -> None:
        """
        Reset model for a new replication.
        
        Reloads the program from source with new seed.
        
        Args:
            seed: Random seed for this replication
        """
        if seed is not None:
            self._current_seed = seed
        
        # Reload program with new seed
        self._loaded = load_file(self._model_path, seed=self._current_seed)
        
        # Create stepper with main rule
        if self._loaded.main_rule_name is None:
            raise ValueError(f"Model {self._model_path} has no main rule")
        
        main_rule = self._loaded.rules.get(self._loaded.main_rule_name)
        if main_rule is None:
            raise ValueError(f"Main rule '{self._loaded.main_rule_name}' not found")
        
        config = StepperConfig(time_var=self._time_var)
        
        self._stepper = ASMStepper(
            state=self._loaded.state,
            main_rule=main_rule,
            rule_evaluator=self._loaded.rule_evaluator,
            config=config,
        )
        
        logger.debug(f"Reset model with seed {self._current_seed}")
    
    def step(self) -> bool:
        """
        Execute one simulation step.
        
        Returns:
            True if step was executed, False if simulation should stop
        """
        if self._stepper is None:
            return False
        return self._stepper.step()
    
    def run(self, end_time: float, on_step: Optional[callable] = None) -> None:
        """
        Run simulation until end_time.
        
        Args:
            end_time: Simulation time to run until
            on_step: Optional callback(state, sim_time) called after each step
        """
        if self._stepper is None:
            raise ValueError("Model not initialized. Call reset() first.")
        
        if on_step is None:
            # Fast path - no callbacks
            self._stepper.run_until(end_time)
        else:
            # Step-by-step with callbacks for statistics collection
            while self.sim_time < end_time:
                stepped = self._stepper.step()
                if not stepped:
                    break
                on_step(self._loaded.state, self.sim_time)
    
    @property
    def sim_time(self) -> float:
        """Current simulation time."""
        if self._stepper is None:
            return 0.0
        return self._stepper.sim_time
    
    @property
    def step_count(self) -> int:
        """Number of steps executed."""
        if self._stepper is None:
            return 0
        return self._stepper.step_count
    
    @property
    def state(self):
        """Access to model state for statistics collection."""
        if self._loaded is None:
            return None
        return self._loaded.state
    
    @property
    def term_evaluator(self):
        """Access to term evaluator for expression evaluation."""
        if self._loaded is None:
            return None
        return self._loaded.term_evaluator


class ExperimenterEngine:
    """
    Engine that executes experiment specifications.
    
    Orchestrates:
    1. Parse experiment specification
    2. Load model
    3. Configure experiment
    4. Run replications
    5. Output results
    
    Usage:
        engine = ExperimenterEngine("experiments/mmn.simasm")
        result = engine.run()
        
        # Or with ExperimentNode directly
        engine = ExperimenterEngine(experiment_node)
        result = engine.run()
    """
    
    def __init__(
        self,
        spec: Union[str, Path, ExperimentNode],
        base_path: Optional[Path] = None,
    ):
        """
        Create engine from experiment specification.
        
        Args:
            spec: Path to experiment .simasm file or ExperimentNode
            base_path: Base path for resolving relative model paths
        """
        if isinstance(spec, ExperimentNode):
            self._spec = spec
            self._base_path = base_path or Path.cwd()
        else:
            # Parse experiment file
            spec_path = Path(spec).resolve()  # Use absolute path
            parser = ExperimentParser()
            self._spec = parser.parse_file(str(spec_path))
            self._base_path = base_path or spec_path.parent

        self._result: Optional[ExperimentResult] = None
    
    @property
    def spec(self) -> ExperimentNode:
        """Return the experiment specification."""
        return self._spec
    
    @property
    def result(self) -> Optional[ExperimentResult]:
        """Return the experiment result (None if not yet run)."""
        return self._result
    
    def run(
        self,
        progress_callback=None,
    ) -> ExperimentResult:
        """
        Run the experiment.
        
        Args:
            progress_callback: Optional callback(rep_id, total) for progress
        
        Returns:
            ExperimentResult with all results
        """
        logger.info(f"Running experiment: {self._spec.name}")
        start_time = time.time()

        # Resolve model path (check sibling models/ folder)
        model_path = self._resolve_path(self._spec.model_path, is_model=True)
        logger.info(f"Loading model: {model_path}")
        
        # Build experiment configuration
        config = self._build_config(model_path)
        
        # Create model adapter
        model = SimASMModel(str(model_path))
        
        # Run replications
        results = self._run_replications(
            model=model,
            config=config,
            progress_callback=progress_callback,
        )
        
        # Build result
        total_time = time.time() - start_time
        summary = self._compute_summary(results)
        
        self._result = ExperimentResult(
            config=config,
            replications=results,
            summary=summary,
            total_wall_time=total_time,
        )
        
        logger.info(f"Experiment completed in {total_time:.2f}s")

        # Create timestamped output directory and generate plots if configured
        output_dir = None
        if config.replications.generate_plots:
            output_dir = self._create_output_directory()
            self._generate_plots(self._result, output_dir)

        # Write output if configured
        if self._spec.output.file_path:
            # Use the same output directory if plots were generated
            if output_dir:
                self._write_output_to_dir(output_dir)
            else:
                self._write_output()

        return self._result
    
    def _resolve_path(self, path: str, is_model: bool = False) -> Path:
        """
        Resolve a path relative to base_path.

        Args:
            path: The path to resolve
            is_model: If True, also check sibling 'models/' folder

        Returns:
            Resolved absolute path
        """
        p = Path(path)
        if p.is_absolute():
            return p

        # Direct relative path
        direct_path = self._base_path / p
        if direct_path.exists():
            return direct_path

        # For models, also check sibling 'models/' folder
        if is_model:
            # If base_path is .../input/experiments, check .../input/models
            models_path = self._base_path.parent / "models" / p.name
            if models_path.exists():
                return models_path

        # Fall back to direct path (even if doesn't exist, for error messages)
        return direct_path

    def _compute_output_path(self) -> Path:
        """
        Compute automatic output path based on spec file location.

        If spec is in .../input/experiments/, output goes to .../output/
        Otherwise uses the path specified in the spec.
        """
        spec_output = self._spec.output.file_path
        if not spec_output:
            return None

        # Check if we're in an input/experiments structure
        if "input" in self._base_path.parts:
            # Find the input folder and compute sibling output folder
            parts = list(self._base_path.parts)
            try:
                input_idx = parts.index("input")
                # Replace input/... with output/
                output_base = Path(*parts[:input_idx]) / "output"
                # Use just the filename from spec_output
                output_filename = Path(spec_output).name
                return output_base / output_filename
            except ValueError:
                pass

        # Fall back to resolving relative to base_path
        return self._resolve_path(spec_output)

    def _build_config(self, model_path: Path) -> ExperimentConfig:
        """Build ExperimentConfig from specification."""
        rep = self._spec.replication
        
        # Build statistic configs
        statistics = []
        for stat in self._spec.statistics:
            stat_config = StatisticConfig(
                name=stat.name,
                type=stat.stat_type,
                expr=stat.expression,
                domain=stat.domain,
                condition=stat.condition,
                interval=stat.interval,
                aggregation=stat.aggregation,
                start_expr=stat.start_expr,
                end_expr=stat.end_expr,
                entity_domain=stat.entity_domain,
                trace=stat.trace,
            )
            statistics.append(stat_config)

        return ExperimentConfig(
            name=self._spec.name,
            model_path=str(model_path),
            replications=ReplicationSettings(
                count=rep.count,
                warmup=rep.warm_up_time,
                length=rep.run_length,
                base_seed=rep.base_seed,
                generate_plots=rep.generate_plots,
                trace_interval=rep.trace_interval,
            ),
            statistics=statistics,
            output_format=self._spec.output.format,
            output_path=self._spec.output.file_path,
        )
    
    def _run_replications(
        self,
        model: SimASMModel,
        config: ExperimentConfig,
        progress_callback=None,
    ) -> List[ReplicationResult]:
        """Run all replications with proper statistics collection."""
        results = []
        rep_settings = self._spec.replication
        
        for i in range(rep_settings.count):
            rep_id = i + 1
            seed = rep_settings.get_seed(i)
            
            if progress_callback:
                progress_callback(rep_id, rep_settings.count)
            
            logger.debug(f"Running replication {rep_id}/{rep_settings.count} (seed={seed})")
            
            rep_start = time.time()
            
            # Reset model
            model.reset(seed=seed)
            
            # Create statistics collector for this replication
            from simasm.core.terms import Environment
            collector = StatisticsCollector(
                configs=config.statistics,
                state=model.state,
                term_evaluator=model.term_evaluator,
                environment=Environment(),
            )

            # Configure trace collection
            warmup = config.replications.warmup
            end_time = config.replications.length
            collector.set_trace_config(
                warmup_time=warmup,
                trace_interval=config.replications.trace_interval
            )

            # Run with step-by-step statistics collection
            def on_step(state, sim_time):
                # Collect statistics at every step (collector handles warmup internally)
                collector.on_step(state, sim_time)

            model.run(end_time=end_time, on_step=on_step)

            # Finalize statistics
            collector.finalize(end_time=end_time, warmup_time=warmup)

            # Get statistic values and traces
            statistics = collector.get_values()
            stat_results = collector.get_results()

            # Extract trace data from results
            traces = {}
            for name, stat_result in stat_results.items():
                if stat_result.raw_values:
                    traces[name] = stat_result.raw_values

            wall_time = time.time() - rep_start

            results.append(ReplicationResult(
                replication_id=rep_id,
                seed=seed,
                statistics=statistics,
                traces=traces,
                final_time=model.sim_time,
                steps_taken=model.step_count,
                wall_time=wall_time,
            ))
        
        return results
    
    def _collect_statistics(
        self,
        model: SimASMModel,
        config: ExperimentConfig,
    ) -> Dict[str, Any]:
        """
        Collect statistics from model state (legacy method, kept for compatibility).
        """
        stats = {}
        
        if model.state is None:
            return stats
        
        for stat_config in config.statistics:
            stats[stat_config.name] = 0.0
        
        return stats
    
    def _compute_summary(
        self,
        results: List[ReplicationResult],
    ) -> Dict[str, SummaryStatistics]:
        """Compute summary statistics across replications."""
        from math import sqrt
        import statistics as pystats
        
        if not results:
            return {}
        
        summary = {}
        stat_names = list(results[0].statistics.keys())
        
        # T-values for 95% CI
        t_values = {
            1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
            6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
            15: 2.131, 20: 2.086, 25: 2.060, 29: 2.045,
        }
        
        for name in stat_names:
            values = []
            for r in results:
                v = r.statistics.get(name)
                if isinstance(v, (int, float)) and v is not None:
                    values.append(float(v))
            
            if not values:
                continue
            
            n = len(values)
            mean = pystats.mean(values)
            min_val = min(values)
            max_val = max(values)
            
            if n > 1:
                std = pystats.stdev(values)
                df = n - 1
                t_val = t_values.get(df, 1.96) if df < 30 else 1.96
                margin = t_val * std / sqrt(n)
                ci_lower = mean - margin
                ci_upper = mean + margin
            else:
                std = 0.0
                ci_lower = mean
                ci_upper = mean
            
            summary[name] = SummaryStatistics(
                mean=mean,
                std_dev=std,
                min_val=min_val,
                max_val=max_val,
                ci_lower=ci_lower,
                ci_upper=ci_upper,
                n=n,
            )
        
        return summary
    
    def _write_output(self) -> None:
        """Write results to output file."""
        if self._result is None:
            return

        # Use automatic output path computation
        output_path = self._compute_output_path()
        if output_path is None:
            return

        output_path.parent.mkdir(parents=True, exist_ok=True)

        write_results(
            self._result,
            output_path,
            format=self._spec.output.format,
        )

        logger.info(f"Wrote results to {output_path}")

    def _create_output_directory(self) -> Path:
        """
        Create timestamped output directory for experiment results.

        Returns:
            Path to created directory
        """
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dir_name = f"{timestamp}_{self._spec.name}"

        # Create directory in simasm/output/
        output_base = Path("simasm/output")
        output_dir = output_base / dir_name
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Created output directory: {output_dir}")
        return output_dir

    def _generate_plots(self, result: ExperimentResult, output_dir: Path) -> None:
        """
        Generate plots for experiment results.

        Args:
            result: Experiment result
            output_dir: Directory to save plots
        """
        try:
            from simasm.simulation.plotting import generate_experiment_plots

            logger.info("Generating plots...")
            generate_experiment_plots(result, output_dir)
        except ImportError as e:
            logger.error(f"Failed to import plotting module: {e}")
            logger.error("Make sure matplotlib and scipy are installed: pip install scipy matplotlib")
        except Exception as e:
            logger.error(f"Failed to generate plots: {e}", exc_info=True)

    def _write_output_to_dir(self, output_dir: Path) -> None:
        """
        Write results to the specified output directory.

        Args:
            output_dir: Directory to write results
        """
        if self._result is None:
            return

        # Determine output filename from format
        ext = self._spec.output.format
        if ext == "json":
            filename = f"{self._spec.name}_results.json"
        elif ext == "csv":
            filename = f"{self._spec.name}_results.csv"
        elif ext == "md":
            filename = f"{self._spec.name}_results.md"
        else:
            filename = f"{self._spec.name}_results.txt"

        output_path = output_dir / filename

        write_results(
            self._result,
            output_path,
            format=self._spec.output.format,
        )

        logger.info(f"Wrote results to {output_path}")


def run_experiment(
    spec_path: str,
    progress_callback=None,
) -> ExperimentResult:
    """
    Convenience function to run an experiment from file.
    
    Args:
        spec_path: Path to experiment .simasm file
        progress_callback: Optional progress callback
    
    Returns:
        ExperimentResult
    
    Example:
        result = run_experiment("experiments/mmn.simasm")
        print(f"Mean queue length: {result.summary['avg_queue'].mean}")
    """
    engine = ExperimenterEngine(spec_path)
    return engine.run(progress_callback=progress_callback)


def run_experiment_from_node(
    spec: ExperimentNode,
    base_path: Optional[Path] = None,
    progress_callback=None,
) -> ExperimentResult:
    """
    Run experiment from ExperimentNode directly.
    
    Args:
        spec: ExperimentNode specification
        base_path: Base path for resolving model paths
        progress_callback: Optional progress callback
    
    Returns:
        ExperimentResult
    """
    engine = ExperimenterEngine(spec, base_path=base_path)
    return engine.run(progress_callback=progress_callback)


# ============================================================================
# Verification Engine
# ============================================================================

from dataclasses import dataclass, field
from enum import Enum

from simasm.verification.label import Label, LabelingFunction
from simasm.verification.trace import (
    Trace, no_stutter_trace, traces_stutter_equivalent, count_stutter_steps
)

from .ast import (
    VerificationNode,
    ModelImportNode,
    LabelNode,
    ObservableNode,
    TimeseriesObservableNode,
    TimeseriesPlotConfigNode,
    VerificationCheckNode,
    VerificationOutputNode,
)
from .transformer import VerificationParser

from simasm.verification.numeric_trace import NumericTrace, NumericTraceResult


class VerificationStatus(Enum):
    """Status of verification result."""
    EQUIVALENT = "equivalent"
    NOT_EQUIVALENT = "not_equivalent"
    ERROR = "error"


@dataclass
class PerSeedStats:
    """
    Statistics for a single seed verification.

    Attributes:
        seed: Random seed used
        is_equivalent: Whether traces were equivalent for this seed
        model_stats: Per-model statistics for this seed
        model_timing: Per-model timing data for this seed
    """
    seed: int
    is_equivalent: bool
    model_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    model_timing: Dict[str, Dict[str, float]] = field(default_factory=dict)


@dataclass
class TraceVerificationResult:
    """
    Result of trace comparison verification.

    Attributes:
        is_equivalent: Whether the models are W-stutter equivalent
        status: Verification status enum
        model_stats: Per-model statistics (raw length, no-stutter length, etc.)
        model_timing: Per-model timing data (load_time_sec, exec_time_sec, total_time_sec)
        first_difference_pos: Position of first difference (if not equivalent)
        time_elapsed: Wall-clock time for verification
        message: Human-readable result message
        per_seed_stats: List of per-seed statistics (for multi-seed verification)
        num_seeds: Number of seeds verified
        equivalent_count: Number of seeds that verified equivalent
        failed_seeds: List of seeds that failed verification
        numeric_traces: Numeric timeseries traces per model per seed
    """
    is_equivalent: bool
    status: VerificationStatus
    model_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    model_timing: Dict[str, Dict[str, float]] = field(default_factory=dict)
    first_difference_pos: Optional[int] = None
    time_elapsed: float = 0.0
    message: str = ""
    per_seed_stats: List[PerSeedStats] = field(default_factory=list)
    num_seeds: int = 1
    equivalent_count: int = 0
    failed_seeds: List[int] = field(default_factory=list)
    numeric_traces: Dict[str, Dict[int, Any]] = field(default_factory=dict)  # model -> seed -> NumericTrace


class VerificationEngine:
    """
    Engine that executes verification specifications via trace comparison.

    Orchestrates:
    1. Parse verification specification
    2. Load models with same seed
    3. Run models and collect traces with labeling functions
    4. Compute no-stutter traces and compare
    5. Output results

    Usage:
        engine = VerificationEngine("verify/eg_vs_acd.simasm")
        result = engine.run()

        if result.is_equivalent:
            print("Models are W-stutter equivalent!")
        else:
            print(f"Difference at position {result.first_difference_pos}")
    """

    def __init__(
        self,
        spec: Union[str, Path, VerificationNode],
        base_path: Optional[Path] = None,
    ):
        """
        Create engine from verification specification.

        Args:
            spec: Path to verification .simasm file or VerificationNode
            base_path: Base path for resolving relative model paths
        """
        if isinstance(spec, VerificationNode):
            self._spec = spec
            self._base_path = base_path or Path.cwd()
        else:
            # Parse verification file
            spec_path = Path(spec).resolve()  # Use absolute path
            parser = VerificationParser()
            self._spec = parser.parse_file(str(spec_path))
            self._base_path = base_path or spec_path.parent

        self._result: Optional[TraceVerificationResult] = None
        self._model_traces: Dict[str, Trace] = {}
        self._ns_traces: Dict[str, Trace] = {}
        self._numeric_traces: Dict[str, Dict[int, NumericTrace]] = {}  # model -> seed -> trace

    @property
    def spec(self) -> VerificationNode:
        """Return the verification specification."""
        return self._spec

    @property
    def result(self) -> Optional[TraceVerificationResult]:
        """Return the verification result (None if not yet run)."""
        return self._result

    def run(
        self,
        progress_callback=None,
    ) -> TraceVerificationResult:
        """
        Run W-stutter equivalence verification via trace comparison.

        Supports multi-seed verification: if spec.seeds has multiple seeds,
        runs verification for all seeds and reports aggregate results.

        Args:
            progress_callback: Optional callback(model_name, message) for progress

        Returns:
            TraceVerificationResult
        """
        import time as time_module
        start_time = time_module.time()

        logger.info(f"Running verification: {self._spec.name}")

        # Check we have exactly 2 models
        if len(self._spec.models) != 2:
            raise ValueError(
                f"Verification requires exactly 2 models, got {len(self._spec.models)}"
            )

        end_time = self._spec.check.run_length
        seeds = self._spec.seeds

        # Multi-seed verification
        if len(seeds) > 1:
            return self._run_multi_seed_verification(seeds, end_time, progress_callback, start_time)

        # Single seed verification (original behavior)
        return self._run_single_seed_verification(seeds[0], end_time, progress_callback, start_time)

    def _run_single_seed_verification(
        self,
        seed: int,
        end_time: float,
        progress_callback,
        start_time: float,
    ) -> TraceVerificationResult:
        """Run verification for a single seed."""
        import time as time_module

        # Run each model and collect traces
        model_stats = {}
        model_timing = {}

        for model_import in self._spec.models:
            model_path = self._resolve_path(model_import.path, is_model=True)
            logger.info(f"Running model '{model_import.name}' from {model_path}")

            if progress_callback:
                progress_callback(model_import.name, "Loading model...")

            # Get labels for this model
            model_labels = [l for l in self._spec.labels if l.model == model_import.name]

            # Get numeric observables for this model
            model_numeric_obs = [
                obs for obs in self._spec.timeseries_observables
                if obs.model == model_import.name
            ]

            # Run and collect trace
            trace, raw_stats, numeric_traces = self._run_model_trace(
                str(model_path),
                model_import.name,
                model_labels,
                seed,
                end_time,
                numeric_observables=model_numeric_obs if model_numeric_obs else None,
            )

            self._model_traces[model_import.name] = trace
            model_stats[model_import.name] = raw_stats

            # Extract timing data
            model_timing[model_import.name] = {
                "load_time_sec": raw_stats["load_time_sec"],
                "exec_time_sec": raw_stats["exec_time_sec"],
                "total_time_sec": raw_stats["total_time_sec"],
            }

            # Store numeric traces
            if numeric_traces:
                if model_import.name not in self._numeric_traces:
                    self._numeric_traces[model_import.name] = {}
                for obs_name, num_trace in numeric_traces.items():
                    if obs_name not in self._numeric_traces[model_import.name]:
                        self._numeric_traces[model_import.name][obs_name] = {}
                    self._numeric_traces[model_import.name][obs_name][seed] = num_trace

            if progress_callback:
                progress_callback(model_import.name, f"Completed {raw_stats['steps']} steps")

        # Compute no-stutter traces
        logger.info("Computing no-stutter traces...")
        for name, trace in self._model_traces.items():
            ns = no_stutter_trace(trace)
            self._ns_traces[name] = ns
            model_stats[name]["raw_length"] = len(trace)
            model_stats[name]["ns_length"] = len(ns)
            model_stats[name]["stutter_steps"] = count_stutter_steps(trace)
            logger.info(
                f"  {name}: {len(trace)} raw -> {len(ns)} no-stutter "
                f"({model_stats[name]['stutter_steps']} stutter steps)"
            )

        # Compare no-stutter traces
        model_names = list(self._ns_traces.keys())
        name_a, name_b = model_names[0], model_names[1]
        ns_a, ns_b = self._ns_traces[name_a], self._ns_traces[name_b]

        is_equivalent = traces_stutter_equivalent(
            self._model_traces[name_a],
            self._model_traces[name_b]
        )

        # Find first difference position if not equivalent
        first_diff = None
        if not is_equivalent:
            for i in range(min(len(ns_a), len(ns_b))):
                if ns_a[i] != ns_b[i]:
                    first_diff = i
                    break
            if first_diff is None and len(ns_a) != len(ns_b):
                first_diff = min(len(ns_a), len(ns_b))

        elapsed = time_module.time() - start_time

        # Build result
        if is_equivalent:
            status = VerificationStatus.EQUIVALENT
            message = f"Models are W-STUTTER EQUIVALENT (verified over {end_time}s simulation)"
        else:
            status = VerificationStatus.NOT_EQUIVALENT
            message = f"Models are NOT W-stutter equivalent (first difference at position {first_diff})"

        self._result = TraceVerificationResult(
            is_equivalent=is_equivalent,
            status=status,
            model_stats=model_stats,
            model_timing=model_timing,
            first_difference_pos=first_diff,
            time_elapsed=elapsed,
            message=message,
            numeric_traces=self._numeric_traces,
        )

        logger.info(f"Verification completed: {status.name}")

        # Generate plots if configured
        if self._spec.output.generate_plots:
            self._generate_verification_plots()

        # Generate timeseries plots if configured
        if self._spec.timeseries_plot_config:
            self._generate_timeseries_plots([seed])

        # Write output if configured
        if self._spec.output.file_path:
            self._write_output()

        return self._result

    def _run_multi_seed_verification(
        self,
        seeds: list,
        end_time: float,
        progress_callback,
        start_time: float,
    ) -> TraceVerificationResult:
        """Run verification for multiple seeds and aggregate results."""
        import time as time_module

        logger.info(f"Running multi-seed verification for {len(seeds)} seeds")

        if progress_callback:
            progress_callback("Multi-seed", f"Running {len(seeds)} seeds...")

        per_seed_stats = []
        failed_seeds = []

        for i, seed in enumerate(seeds):
            if progress_callback:
                progress_callback("Multi-seed", f"Seed {seed} ({i+1}/{len(seeds)})...")

            # Clear traces for each seed
            self._model_traces = {}
            self._ns_traces = {}

            # Run each model with this seed
            model_stats = {}
            seed_timing = {}
            for model_import in self._spec.models:
                model_path = self._resolve_path(model_import.path, is_model=True)
                model_labels = [l for l in self._spec.labels if l.model == model_import.name]

                # Get numeric observables for this model
                model_numeric_obs = [
                    obs for obs in self._spec.timeseries_observables
                    if obs.model == model_import.name
                ]

                trace, raw_stats, numeric_traces = self._run_model_trace(
                    str(model_path),
                    model_import.name,
                    model_labels,
                    seed,
                    end_time,
                    numeric_observables=model_numeric_obs if model_numeric_obs else None,
                )

                self._model_traces[model_import.name] = trace
                model_stats[model_import.name] = raw_stats

                # Extract timing data for this seed
                seed_timing[model_import.name] = {
                    "load_time_sec": raw_stats["load_time_sec"],
                    "exec_time_sec": raw_stats["exec_time_sec"],
                    "total_time_sec": raw_stats["total_time_sec"],
                }

                # Store numeric traces
                if numeric_traces:
                    if model_import.name not in self._numeric_traces:
                        self._numeric_traces[model_import.name] = {}
                    for obs_name, num_trace in numeric_traces.items():
                        if obs_name not in self._numeric_traces[model_import.name]:
                            self._numeric_traces[model_import.name][obs_name] = {}
                        self._numeric_traces[model_import.name][obs_name][seed] = num_trace

            # Compute no-stutter traces
            for name, trace in self._model_traces.items():
                ns = no_stutter_trace(trace)
                self._ns_traces[name] = ns
                model_stats[name]["raw_length"] = len(trace)
                model_stats[name]["ns_length"] = len(ns)
                model_stats[name]["stutter_steps"] = count_stutter_steps(trace)

            # Compare no-stutter traces
            model_names = list(self._ns_traces.keys())
            name_a, name_b = model_names[0], model_names[1]

            is_equivalent = traces_stutter_equivalent(
                self._model_traces[name_a],
                self._model_traces[name_b]
            )

            # Store per-seed stats using the dataclass
            per_seed_stats.append(PerSeedStats(
                seed=seed,
                is_equivalent=is_equivalent,
                model_stats=model_stats.copy(),
                model_timing=seed_timing.copy(),
            ))

            if not is_equivalent:
                failed_seeds.append(seed)

            logger.info(f"  Seed {seed}: {'EQUIVALENT' if is_equivalent else 'NOT EQUIVALENT'}")

        elapsed = time_module.time() - start_time

        # Aggregate results
        all_equivalent = len(failed_seeds) == 0
        equivalent_count = len(seeds) - len(failed_seeds)

        # Compute average statistics
        model_names = list(per_seed_stats[0].model_stats.keys())
        avg_stats = {}
        avg_timing = {}
        for name in model_names:
            raw_lengths = [s.model_stats[name]["raw_length"] for s in per_seed_stats]
            ns_lengths = [s.model_stats[name]["ns_length"] for s in per_seed_stats]
            stutter_steps = [s.model_stats[name]["stutter_steps"] for s in per_seed_stats]

            avg_stats[name] = {
                "avg_raw_length": sum(raw_lengths) / len(raw_lengths),
                "avg_ns_length": sum(ns_lengths) / len(ns_lengths),
                "avg_stutter_steps": sum(stutter_steps) / len(stutter_steps),
                "raw_length": sum(raw_lengths) / len(raw_lengths),  # For compatibility
                "ns_length": sum(ns_lengths) / len(ns_lengths),  # For compatibility
            }

            # Compute average timing
            load_times = [s.model_timing[name]["load_time_sec"] for s in per_seed_stats]
            exec_times = [s.model_timing[name]["exec_time_sec"] for s in per_seed_stats]
            total_times = [s.model_timing[name]["total_time_sec"] for s in per_seed_stats]

            avg_timing[name] = {
                "avg_load_time_sec": sum(load_times) / len(load_times),
                "avg_exec_time_sec": sum(exec_times) / len(exec_times),
                "avg_total_time_sec": sum(total_times) / len(total_times),
                "total_all_seeds_sec": sum(total_times),
            }

        # Build result
        if all_equivalent:
            status = VerificationStatus.EQUIVALENT
            message = f"Models are W-STUTTER EQUIVALENT (verified over {len(seeds)} seeds, {end_time}s each)"
        else:
            status = VerificationStatus.NOT_EQUIVALENT
            message = f"Models are NOT W-stutter equivalent ({equivalent_count}/{len(seeds)} seeds passed, failed: {failed_seeds})"

        self._result = TraceVerificationResult(
            is_equivalent=all_equivalent,
            status=status,
            model_stats=avg_stats,
            model_timing=avg_timing,
            first_difference_pos=None,
            time_elapsed=elapsed,
            message=message,
            per_seed_stats=per_seed_stats,
            num_seeds=len(seeds),
            equivalent_count=equivalent_count,
            failed_seeds=failed_seeds,
            numeric_traces=self._numeric_traces,
        )

        logger.info(f"Multi-seed verification completed: {equivalent_count}/{len(seeds)} equivalent")

        # Generate plots if configured
        if self._spec.output.generate_plots:
            self._generate_verification_plots()

        # Generate timeseries plots if configured
        if self._spec.timeseries_plot_config:
            self._generate_timeseries_plots(seeds)

        # Write output if configured
        if self._spec.output.file_path:
            self._write_output()

        return self._result

    def _run_model_trace(
        self,
        model_path: str,
        model_name: str,
        label_nodes: list,
        seed: int,
        end_time: float,
        numeric_observables: Optional[List[TimeseriesObservableNode]] = None,
    ) -> tuple:
        """
        Run a model and collect its trace.

        Args:
            model_path: Path to the .simasm model file
            model_name: Name of the model for logging
            label_nodes: List of LabelNode definitions for this model
            seed: Random seed
            end_time: Simulation end time
            numeric_observables: Optional list of numeric observables to track

        Returns:
            tuple: (Trace, stats dict, Optional[Dict[str, NumericTrace]])
        """
        import time as time_module
        from simasm.core.terms import Environment, LocationTerm

        # Time model loading
        load_start = time_module.perf_counter()
        loaded = load_file(model_path, seed=seed)
        load_time = time_module.perf_counter() - load_start

        # Create labeling function with this model's term evaluator
        labeling = self._create_labeling_function(loaded.term_evaluator, label_nodes)

        # Get main rule
        main_rule = loaded.rules.get(loaded.main_rule_name)

        # Create stepper
        config = StepperConfig(
            time_var="sim_clocktime",
            end_time=end_time,
        )
        stepper = ASMStepper(
            state=loaded.state,
            main_rule=main_rule,
            rule_evaluator=loaded.rule_evaluator,
            config=config,
        )

        # Collect trace
        trace = Trace()

        # Record initial state
        initial_labels = labeling.evaluate(loaded.state)
        trace.append(initial_labels)

        # Time execution loop
        exec_start = time_module.perf_counter()

        # Setup numeric trace collection if observables provided
        numeric_traces: Dict[str, NumericTrace] = {}
        numeric_evaluators = {}

        if numeric_observables:
            from simasm.simulation.collector import parse_expression

            for obs in numeric_observables:
                numeric_traces[obs.name] = NumericTrace(obs.name)
                try:
                    # Parse the expression
                    expr_ast = parse_expression(obs.expression)
                    numeric_evaluators[obs.name] = expr_ast
                except Exception as e:
                    logger.warning(f"Failed to parse numeric observable '{obs.expression}': {e}")

            # Record initial numeric values
            sim_time = loaded.state.get_var("sim_clocktime") or 0.0
            for obs_name, expr_ast in numeric_evaluators.items():
                try:
                    value = loaded.term_evaluator.eval_with_state(
                        expr_ast, Environment(), loaded.state
                    )
                    numeric_traces[obs_name].append(sim_time, float(value))
                except Exception as e:
                    logger.warning(f"Error evaluating '{obs_name}' at init: {e}")

        # Run and collect
        step = 0
        while stepper.can_step():
            stepper.step()
            step += 1
            labels = labeling.evaluate(loaded.state)
            trace.append(labels)

            # Collect numeric values
            if numeric_observables:
                sim_time = loaded.state.get_var("sim_clocktime") or 0.0
                for obs_name, expr_ast in numeric_evaluators.items():
                    try:
                        value = loaded.term_evaluator.eval_with_state(
                            expr_ast, Environment(), loaded.state
                        )
                        numeric_traces[obs_name].append(sim_time, float(value))
                    except Exception as e:
                        pass  # Skip errors during trace collection

        exec_time = time_module.perf_counter() - exec_start

        final_time = loaded.state.get_var("sim_clocktime") or 0.0

        stats = {
            "steps": step,
            "final_time": final_time,
            "load_time_sec": load_time,
            "exec_time_sec": exec_time,
            "total_time_sec": load_time + exec_time,
        }

        if numeric_observables:
            return trace, stats, numeric_traces
        return trace, stats, None

    def _create_labeling_function(
        self,
        term_evaluator,
        label_nodes: list,
    ) -> LabelingFunction:
        """
        Create a LabelingFunction from label definitions.

        Args:
            term_evaluator: The model's term evaluator
            label_nodes: List of LabelNode definitions

        Returns:
            LabelingFunction that evaluates predicates on model state
        """
        from simasm.core.terms import Environment
        from simasm.simulation.collector import parse_expression
        from simasm.core.state import Undefined

        labeling = LabelingFunction()

        def make_evaluator(ast, te, pred_str):
            """Factory function to create an evaluator for a parsed expression AST."""
            def evaluate(state) -> bool:
                try:
                    # Use eval_with_state to evaluate against the current state
                    result = te.eval_with_state(ast, Environment(), state)

                    # Handle Undefined values
                    if isinstance(result, Undefined):
                        return False

                    return bool(result)
                except Exception as e:
                    logger.warning(f"Error evaluating '{pred_str}': {e}")
                    return False
            return evaluate

        for label_node in label_nodes:
            predicate = label_node.predicate.strip()

            # Strip surrounding quotes if present (from verification file syntax)
            if (predicate.startswith('"') and predicate.endswith('"')) or \
               (predicate.startswith("'") and predicate.endswith("'")):
                predicate = predicate[1:-1]

            try:
                # Parse the predicate expression to AST
                predicate_ast = parse_expression(predicate)
                labeling.define(label_node.name, make_evaluator(predicate_ast, term_evaluator, predicate))
            except Exception as e:
                logger.warning(f"Failed to parse predicate '{predicate}': {e}")
                # Define a fallback that always returns False
                labeling.define(label_node.name, lambda s: False)

        return labeling

    def _resolve_path(self, path: str, is_model: bool = False) -> Path:
        """
        Resolve a path relative to base_path.

        Args:
            path: The path to resolve
            is_model: If True, also check sibling 'models/' folder

        Returns:
            Resolved absolute path
        """
        p = Path(path)
        if p.is_absolute():
            return p

        # Direct relative path
        direct_path = self._base_path / p
        if direct_path.exists():
            return direct_path

        # For models, also check sibling 'models/' folder
        if is_model:
            # If base_path is .../input/experiments, check .../input/models
            models_path = self._base_path.parent / "models" / p.name
            if models_path.exists():
                return models_path

        # Fall back to direct path (even if doesn't exist, for error messages)
        return direct_path

    def _create_verification_output_directory(self) -> Path:
        """
        Create timestamped output directory for verification results.

        Returns:
            Path to created directory
        """
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dir_name = f"{timestamp}_{self._spec.name}"

        # Create directory in simasm/output/
        output_base = Path("simasm/output")
        output_dir = output_base / dir_name
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Created verification output directory: {output_dir}")
        return output_dir

    def _generate_verification_plots(self) -> None:
        """
        Generate plots for verification results.

        Creates visualization plots for multi-seed verification results.
        """
        if self._result is None:
            return

        try:
            from simasm.verification.plotting import (
                generate_verification_plots,
                print_verification_summary,
            )

            # Create output directory
            output_dir = self._create_verification_output_directory()

            logger.info("Generating verification plots...")
            generate_verification_plots(self._result, output_dir)

            # Print summary to console
            print_verification_summary(self._result)

        except ImportError as e:
            logger.error(f"Failed to import verification plotting module: {e}")
            logger.error("Make sure matplotlib and scipy are installed: pip install scipy matplotlib")
        except Exception as e:
            logger.error(f"Failed to generate verification plots: {e}", exc_info=True)

    def _generate_timeseries_plots(self, seeds: List[int]) -> None:
        """
        Generate timeseries comparison plots.

        Creates N×2 grid showing raw and no-stutter traces across seeds.

        Args:
            seeds: List of seeds used in verification
        """
        if self._result is None or not self._spec.timeseries_plot_config:
            return

        try:
            from simasm.verification.trace_plotting import (
                plot_trace_comparison_grid,
                TimeseriesPlotConfig,
            )

            config_node = self._spec.timeseries_plot_config
            observable_name = config_node.observable

            # Get model names
            model_names = [m.name for m in self._spec.models]
            if len(model_names) != 2:
                logger.warning("Timeseries plots require exactly 2 models")
                return

            model_a, model_b = model_names[0], model_names[1]

            # Check if we have numeric traces for the observable
            if model_a not in self._numeric_traces or model_b not in self._numeric_traces:
                logger.warning(f"No numeric traces found for timeseries plotting")
                return

            if observable_name not in self._numeric_traces.get(model_a, {}):
                logger.warning(f"Observable '{observable_name}' not found for model {model_a}")
                return

            if observable_name not in self._numeric_traces.get(model_b, {}):
                logger.warning(f"Observable '{observable_name}' not found for model {model_b}")
                return

            # Get traces for each seed
            traces_a = self._numeric_traces[model_a][observable_name]
            traces_b = self._numeric_traces[model_b][observable_name]

            # Filter to requested seeds
            eg_traces = {s: traces_a[s] for s in seeds if s in traces_a}
            acd_traces = {s: traces_b[s] for s in seeds if s in traces_b}

            if not eg_traces or not acd_traces:
                logger.warning("No matching traces found for requested seeds")
                return

            # Create plot config
            plot_config = TimeseriesPlotConfig(
                y_label=config_node.y_label,
                y_min=config_node.y_min,
                y_max=config_node.y_max,
            )

            # Determine output path
            output_dir = self._create_verification_output_directory()
            output_path = output_dir / config_node.output_file

            logger.info(f"Generating timeseries plot: {output_path}")

            # Generate plot
            fig = plot_trace_comparison_grid(
                eg_traces=eg_traces,
                acd_traces=acd_traces,
                seeds=seeds,
                output_path=output_path,
                title=f"Observable State Trajectory: {observable_name}",
                show_raw=config_node.show_raw,
                show_no_stutter=config_node.show_no_stutter,
                config=plot_config,
                eg_label=model_a,
                acd_label=model_b,
            )

            print(f"  Timeseries plot saved to: {output_path}")

            # Close figure to free memory
            import matplotlib.pyplot as plt
            plt.close(fig)

        except ImportError as e:
            logger.error(f"Failed to import trace plotting module: {e}")
            logger.error("Make sure matplotlib is installed: pip install matplotlib")
        except Exception as e:
            logger.error(f"Failed to generate timeseries plots: {e}", exc_info=True)

    def _compute_output_path(self) -> Path:
        """
        Compute automatic output path based on spec file location.

        If spec is in .../input/experiments/, output goes to .../output/
        Otherwise uses the path specified in the spec.
        """
        spec_output = self._spec.output.file_path
        if not spec_output:
            return None

        # Check if we're in an input/experiments structure
        if "input" in self._base_path.parts:
            # Find the input folder and compute sibling output folder
            parts = list(self._base_path.parts)
            try:
                input_idx = parts.index("input")
                # Replace input/... with output/
                output_base = Path(*parts[:input_idx]) / "output"
                # Use just the filename from spec_output
                output_filename = Path(spec_output).name
                return output_base / output_filename
            except ValueError:
                pass

        # Fall back to resolving relative to base_path
        return self._resolve_path(spec_output)

    def _write_output(self) -> None:
        """Write verification results to output file."""
        if self._result is None:
            return

        # Use automatic output path computation
        output_path = self._compute_output_path()
        if output_path is None:
            return

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if self._spec.output.format == "json":
            self._write_json_output(output_path)
        elif self._spec.output.format == "csv":
            self._write_csv_output(output_path)
        elif self._spec.output.format == "txt":
            self._write_text_output(output_path)
        elif self._spec.output.format == "md":
            self._write_markdown_output(output_path)
        else:
            print(f"  Warning: Unknown output format '{self._spec.output.format}', results not saved")
            logger.warning(f"Unknown output format: {self._spec.output.format}")
            return

        print(f"  Output written to: {output_path}")
        logger.info(f"Wrote verification results to {output_path}")

    def _write_json_output(self, path: Path) -> None:
        """Write results in JSON format."""
        import json

        data = {
            "verification": self._spec.name,
            "status": self._result.status.value,
            "is_equivalent": self._result.is_equivalent,
            "run_length": self._spec.check.run_length,
            "time_elapsed": self._result.time_elapsed,
            "message": self._result.message,
        }

        # Add model timing
        data["model_timing"] = self._result.model_timing

        # Check if multi-seed verification
        if self._result.num_seeds > 1:
            data["seeds"] = [s.seed for s in self._result.per_seed_stats]
            data["num_seeds"] = self._result.num_seeds
            data["equivalent_count"] = self._result.equivalent_count
            data["failed_seeds"] = self._result.failed_seeds
            data["average_statistics"] = {
                name: stats
                for name, stats in self._result.model_stats.items()
            }
            # Serialize per_seed_stats properly
            data["seed_results"] = [
                {
                    "seed": s.seed,
                    "is_equivalent": s.is_equivalent,
                    "model_stats": s.model_stats,
                    "model_timing": s.model_timing,
                }
                for s in self._result.per_seed_stats
            ]
        else:
            data["seed"] = self._spec.seed
            data["models"] = {
                name: stats
                for name, stats in self._result.model_stats.items()
            }
            if not self._result.is_equivalent:
                data["first_difference_position"] = self._result.first_difference_pos

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _write_csv_output(self, path: Path) -> None:
        """Write results in CSV format."""
        import csv

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                "verification", "status", "is_equivalent", "seed",
                "run_length", "time_elapsed", "message"
            ])

            # Main result row
            writer.writerow([
                self._spec.name,
                self._result.status.value,
                self._result.is_equivalent,
                self._spec.seed,
                self._spec.check.run_length,
                f"{self._result.time_elapsed:.3f}",
                self._result.message,
            ])

            # Blank row
            writer.writerow([])

            # Model stats header
            writer.writerow(["model", "path", "raw_length", "ns_length", "stutter_steps"])

            # Model stats rows
            for m in self._spec.models:
                stats = self._result.model_stats.get(m.name, {})
                writer.writerow([
                    m.name,
                    m.path,
                    stats.get("raw_length", ""),
                    stats.get("ns_length", ""),
                    stats.get("stutter_steps", ""),
                ])

    def _write_text_output(self, path: Path) -> None:
        """Write results in text format."""
        lines = [
            "=" * 70,
            "W-STUTTER EQUIVALENCE VERIFICATION",
            "=" * 70,
            "",
            f"Verification: {self._spec.name}",
            f"Seed: {self._spec.seed}",
            f"Run length: {self._spec.check.run_length}",
            "",
            "Models:",
        ]

        for name, stats in self._result.model_stats.items():
            lines.append(f"  {name}: {stats['raw_length']} raw -> {stats['ns_length']} no-stutter")

        lines.extend([
            "",
            "=" * 70,
            f"RESULT: {self._result.message}",
            "=" * 70,
        ])

        with open(path, "w") as f:
            f.write("\n".join(lines))

    def _write_markdown_output(self, path: Path) -> None:
        """Write results in Markdown format."""
        lines = [
            f"# Verification Report: {self._spec.name}",
            "",
            f"**Status:** {self._result.status.value}",
            f"**Seed:** {self._spec.seed}",
            f"**Run Length:** {self._spec.check.run_length}",
            f"**Time Elapsed:** {self._result.time_elapsed:.3f}s",
            "",
            "## Models",
            "",
        ]

        for m in self._spec.models:
            stats = self._result.model_stats.get(m.name, {})
            lines.append(f"- **{m.name}:** `{m.path}`")
            lines.append(f"  - Raw trace: {stats.get('raw_length', '?')} positions")
            lines.append(f"  - No-stutter: {stats.get('ns_length', '?')} positions")
            lines.append(f"  - Stutter steps: {stats.get('stutter_steps', '?')}")

        lines.extend(["", "## Result", ""])

        if self._result.is_equivalent:
            lines.append("**[PASS] Models are W-STUTTER EQUIVALENT**")
        else:
            lines.append("**[FAIL] Models are NOT W-stutter equivalent**")
            lines.append(f"First difference at position: {self._result.first_difference_pos}")

        with open(path, "w") as f:
            f.write("\n".join(lines))


def run_verification(
    spec_path: str,
    progress_callback=None,
) -> TraceVerificationResult:
    """
    Convenience function to run a verification from file.

    Args:
        spec_path: Path to verification .simasm file
        progress_callback: Optional progress callback

    Returns:
        TraceVerificationResult

    Example:
        result = run_verification("verify/eg_vs_acd.simasm")
        if result.is_equivalent:
            print("Models are W-stutter equivalent!")
    """
    engine = VerificationEngine(spec_path)
    return engine.run(progress_callback=progress_callback)


def run_verification_from_node(
    spec: VerificationNode,
    base_path: Optional[Path] = None,
    progress_callback=None,
) -> TraceVerificationResult:
    """
    Run verification from VerificationNode directly.

    Args:
        spec: VerificationNode specification
        base_path: Base path for resolving model paths
        progress_callback: Optional progress callback

    Returns:
        TraceVerificationResult
    """
    engine = VerificationEngine(spec, base_path=base_path)
    return engine.run(progress_callback=progress_callback)


# ============================================================================
# Analysis Engine
# ============================================================================

from dataclasses import dataclass, field as dataclass_field
from .ast import (
    AnalysisNode,
    AnalysisModelNode,
    AnalysisMetricsNode,
    AnalysisRuntimeNode,
    AnalysisRegressionNode,
    AnalysisOutputNode,
)
from .transformer import AnalysisParser


@dataclass
class AnalysisResult:
    """Result of a complexity analysis run."""
    name: str
    features: Dict[str, Any] = dataclass_field(default_factory=dict)
    runtime: Dict[str, Any] = dataclass_field(default_factory=dict)
    regression: Dict[str, Any] = dataclass_field(default_factory=dict)
    output_dir: str = ""
    r_squared: float = 0.0
    message: str = ""


class AnalysisEngine:
    """
    Engine that executes complexity analysis specifications.

    Orchestrates:
    1. Parse analysis specification
    2. Load models and run HET analyzer (extract complexity features)
    3. Measure simulation runtime across seeds
    4. Fit regression model
    5. Output results and plots

    Usage:
        engine = AnalysisEngine("analysis/tandem_complexity.simasm")
        result = engine.run()
        print(f"R² = {result.r_squared:.3f}")
    """

    def __init__(
        self,
        spec: Union[str, Path, AnalysisNode],
        base_path: Optional[Path] = None,
    ):
        """
        Create engine from analysis specification.

        Args:
            spec: Path to analysis .simasm file or AnalysisNode
            base_path: Base path for resolving relative model paths
        """
        if isinstance(spec, AnalysisNode):
            self._spec = spec
            self._base_path = base_path or Path.cwd()
        else:
            spec_path = Path(spec).resolve()
            parser = AnalysisParser()
            self._spec = parser.parse_file(str(spec_path))
            self._base_path = base_path or spec_path.parent

        self._result: Optional[AnalysisResult] = None

    @property
    def spec(self) -> AnalysisNode:
        """Return the analysis specification."""
        return self._spec

    @property
    def result(self) -> Optional[AnalysisResult]:
        """Return the analysis result (None if not yet run)."""
        return self._result

    def _resolve_path(self, path: str) -> str:
        """Resolve a relative path against the base path."""
        p = Path(path)
        if not p.is_absolute():
            p = self._base_path / p
        return str(p.resolve())

    def run(self, progress_callback=None) -> AnalysisResult:
        """
        Run complexity analysis.

        Args:
            progress_callback: Optional callback(stage, message)

        Returns:
            AnalysisResult with features, runtime, and regression data
        """
        import time as time_module
        import json
        from datetime import datetime

        start_time = time_module.time()
        logger.info(f"Running analysis: {self._spec.name}")

        # Setup output directory
        output_base = Path(self._resolve_path(self._spec.output.file_path))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = output_base / timestamp
        output_dir.mkdir(parents=True, exist_ok=True)

        print("=" * 70)
        print(f"  COMPLEXITY ANALYSIS: {self._spec.name}")
        print("=" * 70)

        # Resolve model paths
        model_paths = []
        for model in self._spec.models:
            resolved = self._resolve_path(model.path)
            model_paths.append((model.name, resolved))
            print(f"  Model: {model.name} -> {resolved}")

        print(f"  Seeds: {self._spec.runtime.seeds}")
        print(f"  End time: {self._spec.runtime.end_time}")
        print(f"  Output: {output_dir}")

        # Step 1: Extract complexity features
        if progress_callback:
            progress_callback("metrics", "Extracting complexity features...")

        print("\n" + "-" * 70)
        print("  STEP 1: Extracting Complexity Features")
        print("-" * 70)

        features_data = self._extract_features(model_paths)

        # Save features
        self._save_csv(features_data, output_dir / "complexity_features.csv")

        # Step 2: Measure runtime
        if progress_callback:
            progress_callback("runtime", "Measuring simulation runtime...")

        print("\n" + "-" * 70)
        print("  STEP 2: Measuring Runtime")
        print("-" * 70)

        runtime_data = self._measure_runtime(model_paths)
        runtime_summary = self._compute_runtime_summary(runtime_data)

        self._save_csv(runtime_data, output_dir / "runtime_measurements.csv")
        self._save_csv(runtime_summary, output_dir / "runtime_summary.csv")

        # Step 3: Fit regression (optional)
        regression_results = None
        merged_data = None
        r_squared = 0.0

        if self._spec.regression is not None:
            if progress_callback:
                progress_callback("regression", "Fitting regression model...")

            print("\n" + "-" * 70)
            print("  STEP 3: Fitting Regression Model")
            print("-" * 70)

            regression_results, merged_data = self._fit_regression(
                features_data, runtime_summary
            )

            with open(output_dir / "regression_results.json", "w") as f:
                json.dump(regression_results, f, indent=2)
            self._save_csv(merged_data, output_dir / "merged_data.csv")

            r_squared = regression_results["r_squared"]
            print(f"\n  R² = {r_squared:.4f}")
        else:
            print("\n  (Regression skipped - no regression block specified)")

        # Step 4: Generate plots (only if regression was run)
        if self._spec.output.generate_plots and regression_results is not None:
            if progress_callback:
                progress_callback("plots", "Generating plots...")

            print("\n" + "-" * 70)
            print("  STEP 4: Generating Plots")
            print("-" * 70)

            self._generate_plots(merged_data, regression_results, output_dir)

        # Print summary report
        self._print_report(features_data, runtime_summary, regression_results, merged_data)

        total_time = time_module.time() - start_time

        if regression_results is not None:
            message = f"Analysis complete. R² = {r_squared:.4f}"
        else:
            message = "Analysis complete. (No regression)"

        self._result = AnalysisResult(
            name=self._spec.name,
            features=features_data,
            runtime=runtime_summary,
            regression=regression_results if regression_results else {},
            output_dir=str(output_dir),
            r_squared=r_squared,
            message=message,
        )

        print(f"\n  All results saved to: {output_dir}")
        print(f"  Total wall time: {total_time:.3f}s")

        return self._result

    def _extract_features(
        self, model_paths: List[tuple]
    ) -> List[Dict[str, Any]]:
        """Extract HET complexity features for all models."""
        from simasm.complexity.simasm_het_analyzer import analyze_simasm

        features_list = []
        for model_name, model_path in model_paths:
            with open(model_path, "r") as f:
                source = f.read()

            analysis = analyze_simasm(source, model_path)

            # Parse N and formalism from model name
            parts = Path(model_path).stem.split("_")
            n = int(parts[1]) if len(parts) >= 3 else 0
            formalism = parts[2].upper() if len(parts) >= 3 else "UNKNOWN"

            features = {
                "model_name": model_name,
                "n": n,
                "formalism": formalism,
                "filepath": model_path,
                "total_rules": analysis.total_rules,
                "total_het": analysis.total_het,
                "avg_het": round(analysis.avg_het, 2),
                "state_update_density": round(analysis.state_update_density, 2),
                "total_updates": analysis.total_updates,
                "total_conditionals": analysis.total_conditionals,
                "total_let_bindings": analysis.total_let_bindings,
                "total_function_calls": analysis.total_function_calls,
                "total_new_entities": analysis.total_new_entities,
                "total_list_operations": analysis.total_list_operations,
            }
            features_list.append(features)
            print(f"  {model_name}: HET={analysis.total_het}, "
                  f"rules={analysis.total_rules}, updates={analysis.total_updates}")

        return features_list

    def _measure_runtime(
        self, model_paths: List[tuple]
    ) -> List[Dict[str, Any]]:
        """Measure simulation runtime for all models across seeds."""
        import time as time_module

        measurements = []
        end_time = self._spec.runtime.end_time
        seeds = self._spec.runtime.seeds
        time_var = self._spec.runtime.time_var

        for model_name, model_path in model_paths:
            for seed in seeds:
                # Load model
                load_start = time_module.perf_counter()
                loaded = load_file(model_path, seed=seed)
                load_time = time_module.perf_counter() - load_start

                # Create stepper
                main_rule = loaded.rules.get(loaded.main_rule_name)
                config = StepperConfig(
                    time_var=time_var,
                    end_time=end_time,
                )
                stepper = ASMStepper(
                    state=loaded.state,
                    main_rule=main_rule,
                    rule_evaluator=loaded.rule_evaluator,
                    config=config,
                )

                # Run simulation
                exec_start = time_module.perf_counter()
                steps = 0
                while stepper.can_step():
                    stepper.step()
                    steps += 1
                exec_time = time_module.perf_counter() - exec_start

                final_sim_time = loaded.state.get_var(time_var) or 0.0

                # Parse N and formalism
                parts = Path(model_path).stem.split("_")
                n = int(parts[1]) if len(parts) >= 3 else 0
                formalism = parts[2].upper() if len(parts) >= 3 else "UNKNOWN"

                measurements.append({
                    "model_name": model_name,
                    "n": n,
                    "formalism": formalism,
                    "seed": seed,
                    "end_time": end_time,
                    "steps": steps,
                    "final_sim_time": final_sim_time,
                    "load_time_sec": load_time,
                    "exec_time_sec": exec_time,
                    "total_time_sec": load_time + exec_time,
                })

                print(f"  {model_name} seed={seed}: {steps} steps, "
                      f"{exec_time:.3f}s exec")

        return measurements

    def _compute_runtime_summary(
        self, runtime_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Compute mean/std runtime per model."""
        import numpy as np

        # Group by model
        groups = {}
        for row in runtime_data:
            key = row["model_name"]
            if key not in groups:
                groups[key] = {
                    "model_name": row["model_name"],
                    "n": row["n"],
                    "formalism": row["formalism"],
                    "steps_list": [],
                    "exec_times": [],
                    "load_times": [],
                    "total_times": [],
                    "final_sim_times": [],
                }
            groups[key]["steps_list"].append(row["steps"])
            groups[key]["exec_times"].append(row["exec_time_sec"])
            groups[key]["load_times"].append(row["load_time_sec"])
            groups[key]["total_times"].append(row["total_time_sec"])
            groups[key]["final_sim_times"].append(row["final_sim_time"])

        summary = []
        for key, g in groups.items():
            summary.append({
                "model_name": g["model_name"],
                "n": g["n"],
                "formalism": g["formalism"],
                "steps_mean": float(np.mean(g["steps_list"])),
                "steps_std": float(np.std(g["steps_list"])),
                "exec_time_sec_mean": float(np.mean(g["exec_times"])),
                "exec_time_sec_std": float(np.std(g["exec_times"])),
                "load_time_sec_mean": float(np.mean(g["load_times"])),
                "load_time_sec_std": float(np.std(g["load_times"])),
                "total_time_sec_mean": float(np.mean(g["total_times"])),
                "total_time_sec_std": float(np.std(g["total_times"])),
                "final_sim_time_mean": float(np.mean(g["final_sim_times"])),
                "final_sim_time_std": float(np.std(g["final_sim_times"])),
            })

        return summary

    def _fit_regression(
        self,
        features_data: List[Dict[str, Any]],
        runtime_summary: List[Dict[str, Any]],
    ) -> tuple:
        """Fit linear regression: Runtime ~ predictors."""
        import numpy as np
        from scipy import stats

        predictors = self._spec.regression.predictors
        target = self._spec.regression.target

        # Build lookup from model_name -> runtime summary
        runtime_map = {r["model_name"]: r for r in runtime_summary}

        # Merge features with runtime
        merged = []
        for feat in features_data:
            rt = runtime_map.get(feat["model_name"])
            if rt is None:
                continue
            row = {**feat, **rt}
            merged.append(row)

        # Build X and y
        X_data = []
        y_data = []
        for row in merged:
            x_row = [row[p] for p in predictors]
            X_data.append(x_row)
            y_data.append(row[target])

        X = np.array(X_data, dtype=float)
        y = np.array(y_data, dtype=float)

        n_obs = len(y)
        n_features = X.shape[1]

        # Add intercept
        X_int = np.column_stack([np.ones(n_obs), X])

        # OLS fit
        XtX_inv = np.linalg.inv(X_int.T @ X_int)
        beta = XtX_inv @ X_int.T @ y

        y_pred = X_int @ beta
        residuals = y - y_pred

        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)

        r_squared = 1 - (ss_res / ss_tot)
        adj_r_squared = 1 - (1 - r_squared) * (n_obs - 1) / (n_obs - n_features - 1)

        residual_var = ss_res / (n_obs - n_features - 1)
        residual_std = np.sqrt(residual_var)

        se_beta = np.sqrt(np.diag(XtX_inv) * residual_var)
        t_stats = beta / se_beta
        p_values = 2 * (1 - stats.t.cdf(np.abs(t_stats), df=n_obs - n_features - 1))

        ss_reg = ss_tot - ss_res
        ms_reg = ss_reg / n_features
        ms_res = ss_res / (n_obs - n_features - 1)
        f_stat = ms_reg / ms_res
        f_pvalue = 1 - stats.f.cdf(f_stat, n_features, n_obs - n_features - 1)

        feature_names = ["intercept"] + predictors

        regression_results = {
            "r_squared": float(r_squared),
            "adj_r_squared": float(adj_r_squared),
            "coefficients": {n: float(c) for n, c in zip(feature_names, beta)},
            "std_errors": {n: float(s) for n, s in zip(feature_names, se_beta)},
            "t_statistics": {n: float(t) for n, t in zip(feature_names, t_stats)},
            "p_values": {n: float(p) for n, p in zip(feature_names, p_values)},
            "f_statistic": float(f_stat),
            "f_pvalue": float(f_pvalue),
            "n_observations": n_obs,
            "residual_std_error": float(residual_std),
            "predictors": predictors,
            "target": target,
        }

        # Add predictions to merged data
        for i, row in enumerate(merged):
            row["predicted_runtime"] = float(y_pred[i])
            row["residual"] = float(residuals[i])

        return regression_results, merged

    def _generate_plots(
        self,
        merged_data: List[Dict[str, Any]],
        regression_results: Dict[str, Any],
        output_dir: Path,
    ):
        """Generate visualization plots."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("  WARNING: matplotlib not available, skipping plots")
            return

        formalisms = sorted(set(row["formalism"] for row in merged_data))
        colors = {"EG": "blue", "ACD": "orange"}

        fig, axes = plt.subplots(2, 2, figsize=(12, 10))

        # Plot 1: Primary predictor vs Runtime
        primary = regression_results["predictors"][0]
        ax = axes[0, 0]
        for fm in formalisms:
            data = [r for r in merged_data if r["formalism"] == fm]
            ax.scatter(
                [r[primary] for r in data],
                [r["exec_time_sec_mean"] for r in data],
                c=colors.get(fm, "gray"), label=fm, s=80, alpha=0.7,
            )
        ax.set_xlabel(primary)
        ax.set_ylabel("Execution Time (s)")
        ax.set_title(f"{primary} vs Runtime")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Plot 2: Predicted vs Actual
        ax = axes[0, 1]
        for fm in formalisms:
            data = [r for r in merged_data if r["formalism"] == fm]
            ax.scatter(
                [r["predicted_runtime"] for r in data],
                [r["exec_time_sec_mean"] for r in data],
                c=colors.get(fm, "gray"), label=fm, s=80, alpha=0.7,
            )
        all_pred = [r["predicted_runtime"] for r in merged_data]
        all_act = [r["exec_time_sec_mean"] for r in merged_data]
        mn = min(min(all_pred), min(all_act))
        mx = max(max(all_pred), max(all_act))
        ax.plot([mn, mx], [mn, mx], "k--", alpha=0.5, label="Perfect fit")
        ax.set_xlabel("Predicted Runtime (s)")
        ax.set_ylabel("Actual Runtime (s)")
        r2 = regression_results["r_squared"]
        ax.set_title(f"Predicted vs Actual (R\u00b2 = {r2:.3f})")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Plot 3: N vs Runtime
        ax = axes[1, 0]
        for fm in formalisms:
            data = sorted(
                [r for r in merged_data if r["formalism"] == fm],
                key=lambda r: r["n"],
            )
            ax.plot(
                [r["n"] for r in data],
                [r["exec_time_sec_mean"] for r in data],
                "o-", c=colors.get(fm, "gray"), label=fm, markersize=8,
            )
        ax.set_xlabel("Number of Stations (N)")
        ax.set_ylabel("Execution Time (s)")
        ax.set_title("Runtime Scaling with N")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Plot 4: Residuals
        ax = axes[1, 1]
        for fm in formalisms:
            data = [r for r in merged_data if r["formalism"] == fm]
            ax.scatter(
                [r["predicted_runtime"] for r in data],
                [r["residual"] for r in data],
                c=colors.get(fm, "gray"), label=fm, s=80, alpha=0.7,
            )
        ax.axhline(y=0, color="k", linestyle="--", alpha=0.5)
        ax.set_xlabel("Predicted Runtime (s)")
        ax.set_ylabel("Residual (s)")
        ax.set_title("Residual Plot")
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plot_path = output_dir / "complexity_vs_runtime.png"
        plt.savefig(plot_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved plot: {plot_path}")

    def _print_report(
        self,
        features_data: List[Dict[str, Any]],
        runtime_summary: List[Dict[str, Any]],
        regression_results: Optional[Dict[str, Any]],
        merged_data: Optional[List[Dict[str, Any]]],
    ):
        """Print analysis report to console."""
        print("\n" + "=" * 70)
        print(f"  ANALYSIS REPORT: {self._spec.name}")
        print("=" * 70)

        print("\n1. COMPLEXITY FEATURES")
        print("-" * 70)
        print(f"{'Model':<20} {'N':>5} {'Form':>5} {'Rules':>6} "
              f"{'HET':>8} {'Updates':>8} {'Cond':>6}")
        print("-" * 70)
        for row in features_data:
            print(f"{row['model_name']:<20} {row['n']:>5} {row['formalism']:>5} "
                  f"{row['total_rules']:>6} {row['total_het']:>8} "
                  f"{row['total_updates']:>8} {row['total_conditionals']:>6}")

        print("\n2. RUNTIME SUMMARY")
        print("-" * 70)
        print(f"{'Model':<20} {'N':>5} {'Form':>5} {'Steps':>10} "
              f"{'Exec(s)':>10} {'Std':>8}")
        print("-" * 70)
        for row in runtime_summary:
            print(f"{row['model_name']:<20} {row['n']:>5} {row['formalism']:>5} "
                  f"{row['steps_mean']:>10.0f} {row['exec_time_sec_mean']:>10.3f} "
                  f"{row['exec_time_sec_std']:>8.3f}")

        if regression_results is not None:
            r = regression_results
            print("\n3. REGRESSION RESULTS")
            print("-" * 70)
            predictors = r["predictors"]
            print(f"  Model: Runtime ~ {' + '.join(predictors)}")
            print(f"  Observations: {r['n_observations']}")
            print(f"\n  R-squared:         {r['r_squared']:.4f}")
            print(f"  Adjusted R\u00b2:       {r['adj_r_squared']:.4f}")
            print(f"  Residual Std Err:  {r['residual_std_error']:.6f}")
            print(f"  F-statistic:       {r['f_statistic']:.4f}")
            print(f"  F p-value:         {r['f_pvalue']:.6f}")
            print()
            print("  Coefficients:")
            print(f"  {'Variable':<15} {'Coef':>12} {'Std Err':>12} "
                  f"{'t-stat':>10} {'p-value':>12}")
            print("  " + "-" * 61)
            for var in ["intercept"] + predictors:
                print(f"  {var:<15} {r['coefficients'][var]:>12.6f} "
                      f"{r['std_errors'][var]:>12.6f} "
                      f"{r['t_statistics'][var]:>10.3f} "
                      f"{r['p_values'][var]:>12.6f}")

            r2 = r["r_squared"]
            if r2 >= 0.9:
                quality = "EXCELLENT"
            elif r2 >= 0.7:
                quality = "GOOD"
            elif r2 >= 0.5:
                quality = "MODERATE"
            else:
                quality = "WEAK"
            print(f"\n  Predictive Power: {quality} (R\u00b2 = {r2:.3f})")

        print("\n" + "=" * 70)

    @staticmethod
    def _save_csv(data: List[Dict[str, Any]], path: Path):
        """Save list of dicts as CSV."""
        if not data:
            return
        import csv
        keys = data[0].keys()
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
        print(f"  Saved: {path}")


def run_analysis(
    spec_path: str,
    progress_callback=None,
) -> AnalysisResult:
    """
    Convenience function to run a complexity analysis from file.

    Args:
        spec_path: Path to analysis .simasm file
        progress_callback: Optional progress callback

    Returns:
        AnalysisResult

    Example:
        result = run_analysis("analysis/tandem_complexity.simasm")
        print(f"R² = {result.r_squared:.3f}")
    """
    engine = AnalysisEngine(spec_path)
    return engine.run(progress_callback=progress_callback)


def run_analysis_from_node(
    spec: AnalysisNode,
    base_path: Optional[Path] = None,
    progress_callback=None,
) -> AnalysisResult:
    """
    Run analysis from AnalysisNode directly.

    Args:
        spec: AnalysisNode specification
        base_path: Base path for resolving model paths
        progress_callback: Optional progress callback

    Returns:
        AnalysisResult
    """
    engine = AnalysisEngine(spec, base_path=base_path)
    return engine.run(progress_callback=progress_callback)


# =============================================================================
# Complexity Analysis Engine
# =============================================================================

from dataclasses import dataclass, field
from .ast import ComplexityNode, ComplexityModelNode, ComplexityMetricsNode
from .transformer import ComplexityParser


@dataclass
class ComplexityResult:
    """
    Result of complexity analysis.

    Attributes:
        name: Analysis name
        models: List of model results
        summary: Summary statistics
        elapsed_time: Total analysis time in seconds
    """
    name: str
    models: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    elapsed_time: float = 0.0
    metrics: Optional[ComplexityMetricsNode] = None


def _compute_loc(path):
    """Non-blank, non-comment lines in .simasm file."""
    count = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("//"):
                count += 1
    return count


def _compute_kc(path):
    """Kolmogorov complexity approximation: log2(zlib compressed size)."""
    import zlib
    import math
    with open(path, "rb") as f:
        data = f.read()
    compressed = zlib.compress(data, 9)
    return math.log2(len(compressed))


class ComplexityEngine:
    """
    Engine that executes complexity analysis specifications.

    Orchestrates:
    1. Parse complexity specification
    2. Load SimASM models and Event Graph JSON specs
    3. Compute Static HET and Path-Based HET
    4. Compute structural metrics
    5. Output results

    This is focused purely on complexity metric extraction,
    without runtime measurement or regression analysis.

    Usage:
        engine = ComplexityEngine("specs/complexity.simasm")
        result = engine.run()
        print(f"Models analyzed: {len(result.models)}")
    """

    def __init__(
        self,
        spec: Union[str, Path, ComplexityNode],
        base_path: Optional[Path] = None,
    ):
        """
        Create engine from complexity specification.

        Args:
            spec: Path to complexity .simasm file or ComplexityNode
            base_path: Base path for resolving relative model paths
        """
        if isinstance(spec, ComplexityNode):
            self._spec = spec
            self._base_path = base_path or Path.cwd()
        else:
            spec_path = Path(spec).resolve()
            parser = ComplexityParser()
            self._spec = parser.parse_file(str(spec_path))
            self._base_path = base_path or spec_path.parent

        self._result: Optional[ComplexityResult] = None

    @property
    def spec(self) -> ComplexityNode:
        """Return the complexity specification."""
        return self._spec

    @property
    def result(self) -> Optional[ComplexityResult]:
        """Return the complexity result (None if not yet run)."""
        return self._result

    def _resolve_path(self, path: str) -> str:
        """Resolve a relative path against the base path."""
        p = Path(path)
        if not p.is_absolute():
            p = self._base_path / p
        return str(p.resolve())

    def _expand_models(self):
        """Expand directory-based model discovery into ComplexityModelNode list."""
        models = list(self._spec.models)

        if self._spec.simasm_dir:
            simasm_dir = Path(self._resolve_path(self._spec.simasm_dir))
            json_dir = Path(self._resolve_path(self._spec.json_dir)) if self._spec.json_dir else None
            for simasm_file in sorted(simasm_dir.rglob("*.simasm")):
                name = simasm_file.stem.replace("_eg", "")
                topology = simasm_file.parent.name
                relative = simasm_file.relative_to(simasm_dir)
                json_file = None
                if json_dir:
                    candidate = json_dir / relative.with_suffix(".json")
                    if candidate.exists():
                        json_file = str(candidate)
                model = ComplexityModelNode(name, str(simasm_file), json_file or "", topology=topology)
                models.append(model)

        return models

    def run(self, progress_callback=None) -> ComplexityResult:
        """
        Run complexity analysis.

        Args:
            progress_callback: Optional callback(stage, message)

        Returns:
            ComplexityResult with all computed metrics
        """
        import time as time_module
        import json
        from datetime import datetime

        start_time = time_module.time()
        logger.info(f"Running complexity analysis: {self._spec.name}")

        # Import complexity module
        from simasm.complexity import analyze_complexity, get_all_metrics

        # Expand directory-based models
        all_models = self._expand_models()

        metrics = self._spec.metrics
        verbose = len(all_models) <= 5

        print("=" * 70)
        print(f"  COMPLEXITY ANALYSIS: {self._spec.name}")
        print("=" * 70)

        if not verbose:
            print(f"\n  Analyzing {len(all_models)} models...")

        # Analyze each model
        model_results = []

        for i, model in enumerate(all_models):
            if progress_callback:
                progress_callback("model", f"Analyzing {model.name}...")

            # Resolve paths
            simasm_path = self._resolve_path(model.simasm_path)
            eg_path = self._resolve_path(model.event_graph_path) if model.event_graph_path else None

            if verbose:
                print(f"\n  [{i+1}/{len(all_models)}] {model.name}")
                print(f"      SimASM: {simasm_path}")
                if eg_path:
                    print(f"      Event Graph: {eg_path}")

            try:
                # Run complexity analysis
                result = analyze_complexity(
                    simasm_path,
                    json_spec_path=eg_path,
                    model_name=model.name,
                )

                # Build result dict
                model_result = {
                    "name": model.name,
                    "simasm_path": simasm_path,
                    "event_graph_path": eg_path,
                    "het_static": result.het_static,
                    "het_event": result.het_event,
                    "het_control": result.het_control,
                    "smc": result.smc,
                }

                # Add topology if available
                if model.topology:
                    model_result["topology"] = model.topology

                # Add LOC if enabled
                if metrics.loc:
                    model_result["loc"] = _compute_loc(simasm_path)

                # Add KC if enabled
                if metrics.kc:
                    model_result["kc"] = _compute_kc(simasm_path)

                # Add CC (cyclomatic number) if enabled
                if metrics.cc and eg_path:
                    model_result["cc"] = result.cyclomatic_number

                # Add path-based HET if enabled and computed
                if metrics.het_path_based and eg_path:
                    model_result["het_path_avg"] = result.het_path_avg
                    model_result["num_paths"] = result.num_paths
                    if self._spec.output.include_paths:
                        model_result["path_breakdown"] = [
                            {"path": p, "het": h} for p, h in result.path_breakdown
                        ]

                # Add structural metrics if enabled
                if metrics.structural and eg_path:
                    model_result["vertex_count"] = result.vertex_count
                    model_result["edge_count"] = result.edge_count
                    model_result["edge_density"] = result.edge_density
                    model_result["cyclomatic_number"] = result.cyclomatic_number
                    model_result["has_cycles"] = result.has_cycles

                # Add component breakdown if enabled
                if metrics.component_breakdown:
                    model_result["total_rules"] = result.total_rules
                    model_result["total_updates"] = result.total_updates
                    model_result["total_conditionals"] = result.total_conditionals
                    model_result["total_let_bindings"] = result.total_let_bindings
                    model_result["total_function_calls"] = result.total_function_calls
                    model_result["total_new_entities"] = result.total_new_entities
                    model_result["total_list_operations"] = result.total_list_operations

                    # Per-rule breakdown
                    if hasattr(result, 'rules') and result.rules:
                        model_result["rules"] = [
                            {
                                "name": r.name,
                                "het": r.het,
                                "updates": r.updates,
                                "conditionals": r.conditionals,
                                "let_bindings": r.let_bindings,
                                "function_calls": r.function_calls,
                                "new_entities": r.new_entities,
                                "list_operations": getattr(r, 'list_operations', 0),
                            }
                            for r in result.rules
                        ]

                model_results.append(model_result)

                if verbose:
                    print(f"      SMC: {result.smc:.0f}" if result.smc > 0 else f"      Static HET: {result.het_static}")

            except Exception as e:
                logger.error(f"Error analyzing {model.name}: {e}")
                if verbose:
                    print(f"      ERROR: {e}")
                model_results.append({
                    "name": model.name,
                    "error": str(e),
                })

        # Compute summary statistics
        valid_results = [m for m in model_results if "error" not in m]
        summary = {}

        if valid_results:
            summary["num_models"] = len(valid_results)
            summary["het_static_min"] = min(m["het_static"] for m in valid_results)
            summary["het_static_max"] = max(m["het_static"] for m in valid_results)
            summary["het_static_mean"] = sum(m["het_static"] for m in valid_results) / len(valid_results)

            # SMC summary
            smc_values = [m.get("smc", 0) for m in valid_results if m.get("smc", 0) > 0]
            if smc_values:
                summary["smc_min"] = min(smc_values)
                summary["smc_max"] = max(smc_values)
                summary["smc_mean"] = sum(smc_values) / len(smc_values)

            if metrics.het_path_based:
                path_avg_values = [m.get("het_path_avg", 0) for m in valid_results if "het_path_avg" in m]
                if path_avg_values:
                    summary["het_path_avg_min"] = min(path_avg_values)
                    summary["het_path_avg_max"] = max(path_avg_values)
                    summary["het_path_avg_mean"] = sum(path_avg_values) / len(path_avg_values)

        elapsed_time = time_module.time() - start_time

        self._result = ComplexityResult(
            name=self._spec.name,
            models=model_results,
            summary=summary,
            elapsed_time=elapsed_time,
            metrics=metrics,
        )

        # Write output
        if self._spec.output.format == "json":
            output_path = self._resolve_path(self._spec.output.file_path)
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)

            output_data = {
                "name": self._spec.name,
                "timestamp": datetime.now().isoformat(),
                "models": model_results,
                "summary": summary,
                "elapsed_time_sec": elapsed_time,
            }

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2)

            print(f"\n  Output written to: {output_path}")

        print(f"\n  Analysis completed in {elapsed_time:.2f}s")
        print("=" * 70)

        return self._result


def run_complexity(
    spec_path: str,
    progress_callback=None,
) -> ComplexityResult:
    """
    Convenience function to run complexity analysis from file.

    Args:
        spec_path: Path to complexity .simasm file
        progress_callback: Optional progress callback

    Returns:
        ComplexityResult

    Example:
        result = run_complexity("specs/benchmark_complexity.simasm")
        for model in result.models:
            print(f"{model['name']}: HET={model['het_static']}")
    """
    engine = ComplexityEngine(spec_path)
    return engine.run(progress_callback=progress_callback)


def run_complexity_from_node(
    spec: ComplexityNode,
    base_path: Optional[Path] = None,
    progress_callback=None,
) -> ComplexityResult:
    """
    Run complexity analysis from ComplexityNode directly.

    Args:
        spec: ComplexityNode specification
        base_path: Base path for resolving model paths
        progress_callback: Optional progress callback

    Returns:
        ComplexityResult
    """
    engine = ComplexityEngine(spec, base_path=base_path)
    return engine.run(progress_callback=progress_callback)
