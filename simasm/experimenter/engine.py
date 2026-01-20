"""
experimenter/engine.py

Engine that executes experiment specifications.

Provides:
- SimASMModel: Adapter that wraps LoadedProgram as SimulationModel
- ExperimenterEngine: Orchestrates experiment execution
- run_experiment: Convenience function

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
    VerificationCheckNode,
    VerificationOutputNode,
)
from .transformer import VerificationParser


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
    """
    seed: int
    is_equivalent: bool
    model_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class TraceVerificationResult:
    """
    Result of trace comparison verification.

    Attributes:
        is_equivalent: Whether the models are W-stutter equivalent
        status: Verification status enum
        model_stats: Per-model statistics (raw length, no-stutter length, etc.)
        first_difference_pos: Position of first difference (if not equivalent)
        time_elapsed: Wall-clock time for verification
        message: Human-readable result message
        per_seed_stats: List of per-seed statistics (for multi-seed verification)
        num_seeds: Number of seeds verified
        equivalent_count: Number of seeds that verified equivalent
        failed_seeds: List of seeds that failed verification
    """
    is_equivalent: bool
    status: VerificationStatus
    model_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    first_difference_pos: Optional[int] = None
    time_elapsed: float = 0.0
    message: str = ""
    per_seed_stats: List[PerSeedStats] = field(default_factory=list)
    num_seeds: int = 1
    equivalent_count: int = 0
    failed_seeds: List[int] = field(default_factory=list)


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

        for model_import in self._spec.models:
            model_path = self._resolve_path(model_import.path, is_model=True)
            logger.info(f"Running model '{model_import.name}' from {model_path}")

            if progress_callback:
                progress_callback(model_import.name, "Loading model...")

            # Get labels for this model
            model_labels = [l for l in self._spec.labels if l.model == model_import.name]

            # Run and collect trace
            trace, raw_stats = self._run_model_trace(
                str(model_path),
                model_import.name,
                model_labels,
                seed,
                end_time,
            )

            self._model_traces[model_import.name] = trace
            model_stats[model_import.name] = raw_stats

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
            first_difference_pos=first_diff,
            time_elapsed=elapsed,
            message=message,
        )

        logger.info(f"Verification completed: {status.name}")

        # Generate plots if configured
        if self._spec.output.generate_plots:
            self._generate_verification_plots()

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
            for model_import in self._spec.models:
                model_path = self._resolve_path(model_import.path, is_model=True)
                model_labels = [l for l in self._spec.labels if l.model == model_import.name]

                trace, raw_stats = self._run_model_trace(
                    str(model_path),
                    model_import.name,
                    model_labels,
                    seed,
                    end_time,
                )

                self._model_traces[model_import.name] = trace
                model_stats[model_import.name] = raw_stats

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
            first_difference_pos=None,
            time_elapsed=elapsed,
            message=message,
            per_seed_stats=per_seed_stats,
            num_seeds=len(seeds),
            equivalent_count=equivalent_count,
            failed_seeds=failed_seeds,
        )

        logger.info(f"Multi-seed verification completed: {equivalent_count}/{len(seeds)} equivalent")

        # Generate plots if configured
        if self._spec.output.generate_plots:
            self._generate_verification_plots()

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
    ) -> tuple:
        """
        Run a model and collect its trace.

        Args:
            model_path: Path to the .simasm model file
            model_name: Name of the model for logging
            label_nodes: List of LabelNode definitions for this model
            seed: Random seed
            end_time: Simulation end time

        Returns:
            tuple: (Trace, stats dict)
        """
        from simasm.core.terms import Environment, LocationTerm

        # Load the model
        loaded = load_file(model_path, seed=seed)

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

        # Run and collect
        step = 0
        while stepper.can_step():
            stepper.step()
            step += 1
            labels = labeling.evaluate(loaded.state)
            trace.append(labels)

        final_time = loaded.state.get_var("sim_clocktime") or 0.0

        stats = {
            "steps": step,
            "final_time": final_time,
        }

        return trace, stats

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
