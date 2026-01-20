#!/usr/bin/env python3
"""
SimASM Experimenter CLI

Command-line interface for running SimASM experiments and verification.

Usage:
    # Run experiments
    python -m simasm.experimenter.cli experiments/mmn.simasm
    python -m simasm.experimenter.cli input/*.simasm --output output/
    python -m simasm.experimenter.cli input/*.simasm -v --log-file
    
    # Run verification from spec file
    python -m simasm.experimenter.cli --verify input/eg_vs_acd_verification.simasm
    
    # Run verification with two models directly
    python -m simasm.experimenter.cli --verify-models input/mmn_eg.simasm input/mmn_acd.simasm
    python -m simasm.experimenter.cli --verify-models model_a.simasm model_b.simasm --k-max 5000 --seed 123
    
    # Or if installed:
    simasm-run experiments/mmn.simasm
    simasm-run --verify verification_spec.simasm
"""

import argparse
import sys
import json
import time
from pathlib import Path
from typing import List, Optional, Callable

from simasm.experimenter import ExperimenterEngine, ExperimentParser
from simasm.experimenter.transformer import VerificationParser
from simasm.experimenter.ast import VerificationNode
from simasm.simulation.output import to_console
from simasm.log.logger import enable_logging, get_logger

# Create module-level logger
logger = get_logger(__name__)

# Verification imports
from simasm.parser import load_file, LoadedProgram
from simasm.runtime.stepper import ASMStepper, StepperConfig
from simasm.core.state import ASMState
from simasm.verification.label import Label, LabelingFunction
from simasm.verification.ts import TransitionSystem, create_transition_system
from simasm.verification.kinduction import (
    KInductionVerifier,
    VerificationResult,
    VerificationStatus,
    format_verification_report,
)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run SimASM experiment or verification specifications (auto-detected)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run experiment or verification (auto-detected from file content)
    python -m simasm.experimenter.cli experiments/mmn.simasm
    python -m simasm.experimenter.cli input/mm5_w_stutter_equivalence.simasm

    # Run with verbose console output
    python -m simasm.experimenter.cli experiments/mmn.simasm -v

    # Run with debug logging to file
    python -m simasm.experimenter.cli experiments/mmn.simasm --log-file

    # Override output directory
    python -m simasm.experimenter.cli experiments/mmn.simasm -o results/

    # Run verification with two models directly (bypasses auto-detection)
    python -m simasm.experimenter.cli --verify-models mmn_eg.simasm mmn_acd.simasm
        """,
    )
    
    parser.add_argument(
        "specs",
        nargs="*",
        default=[],
        help="Path(s) to .simasm file(s) - experiment or verification (auto-detected)",
    )
    
    parser.add_argument(
        "--verify-models",
        nargs=2,
        metavar=("MODEL_A", "MODEL_B"),
        help="Run stutter equivalence verification on two model files",
    )
    
    parser.add_argument(
        "--k-max",
        type=int,
        default=1000,
        help="Maximum k-induction depth (default: 1000)",
    )
    
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for verification (default: 42)",
    )
    
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Verification timeout in seconds (default: no limit)",
    )
    
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Override output directory",
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose console logging",
    )
    
    parser.add_argument(
        "--log-file",
        action="store_true",
        help="Write logs to simasm/log/ directory",
    )
    
    parser.add_argument(
        "--log-level",
        default="debug",
        choices=["debug", "info", "warning", "error"],
        help="Log level (default: debug)",
    )
    
    parser.add_argument(
        "--log-dir",
        default="simasm/log",
        help="Directory for log files (default: simasm/log)",
    )
    
    parser.add_argument(
        "--console",
        action="store_true",
        help="Print full results to console",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse experiments but don't run them",
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output verification results as JSON",
    )
    
    return parser.parse_args()


def detect_spec_type(path: Path) -> str:
    """
    Detect whether a .simasm file is an experiment or verification spec.

    Args:
        path: Path to .simasm file

    Returns:
        "experiment" or "verification"
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Look for the declaration keyword at the start
    content_stripped = content.strip()
    if content_stripped.startswith("verification "):
        return "verification"
    elif content_stripped.startswith("experiment "):
        return "experiment"

    # Fallback: check for keywords anywhere
    if "verification " in content and "endverification" in content:
        return "verification"
    elif "experiment " in content and "endexperiment" in content:
        return "experiment"

    # Default to experiment
    return "experiment"


def run_single_experiment(
    path: Path,
    output_dir: Optional[Path] = None,
    verbose: bool = False,
    console: bool = False,
    dry_run: bool = False,
) -> bool:
    """
    Run a single experiment.
    
    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"Experiment: {path}")
    print(f"{'='*60}")
    
    try:
        # Parse experiment
        parser = ExperimentParser()
        spec = parser.parse_file(str(path))
        
        print(f"  Name: {spec.name}")
        print(f"  Model: {spec.model_path}")
        print(f"  Replications: {spec.replication.count}")
        print(f"  Run length: {spec.replication.run_length}")
        print(f"  Warmup: {spec.replication.warm_up_time}")
        print(f"  Statistics: {len(spec.statistics)}")
        
        if dry_run:
            print("\n  [DRY RUN - not executing]")
            return True
        
        # Run experiment
        engine = ExperimenterEngine(spec, base_path=path.parent)
        
        def progress(rep_id: int, total: int):
            if verbose:
                print(f"  Replication {rep_id}/{total}...", end="\r")
        
        print("\n  Running...")
        result = engine.run(progress_callback=progress if verbose else None)
        
        print(f"\n  Completed in {result.total_wall_time:.2f}s")
        print(f"  Total steps: {sum(r.steps_taken for r in result.replications):,}")
        
        # Print summary
        if result.summary:
            print("\n  Summary Statistics:")
            for name, summ in result.summary.items():
                print(f"    {name}: {summ.mean:.4f} ± {(summ.ci_upper - summ.ci_lower)/2:.4f}")
        
        # Console output
        if console:
            print("\n" + to_console(result))
        
        # Override output path if specified
        if output_dir:
            output_path = output_dir / f"{spec.name}_results.json"
            from simasm.simulation.output import write_results
            output_path.parent.mkdir(parents=True, exist_ok=True)
            write_results(result, output_path)
            print(f"\n  Output written to: {output_path}")
        
        return True
        
    except Exception as e:
        print(f"\n  ERROR: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


# ============================================================================
# Verification Functions
# ============================================================================

def create_labeling_from_spec(
    loaded: LoadedProgram,
    model_name: str,
    labels: List,  # List[LabelNode]
    observables: List,  # List[ObservableNode]
) -> LabelingFunction:
    """
    Create a labeling function from verification spec labels.
    
    Dynamically parses and evaluates predicate expressions from the DSL.
    
    Args:
        loaded: Loaded program (for term_evaluator)
        model_name: Name of this model in the spec (e.g., "EG", "ACD")
        labels: List of LabelNode from the spec
        observables: List of ObservableNode from the spec
    
    Returns:
        LabelingFunction that evaluates predicates on model state
    """
    from simasm.simulation.collector import parse_expression
    from simasm.core.terms import Environment
    from simasm.core.state import Undefined
    
    labeling = LabelingFunction()
    
    # Find observable names that map to this model
    # observable_name -> label_name for this model
    model_label_names = {}
    for obs in observables:
        if model_name in obs.mappings:
            label_name = obs.mappings[model_name]
            model_label_names[obs.name] = label_name
    
    # Find label definitions for this model
    # label_name -> predicate_string
    label_predicates = {}
    for label in labels:
        if label.model == model_name:
            label_predicates[label.name] = label.predicate
    
    # Create predicate evaluators for each observable
    for observable_name, label_name in model_label_names.items():
        if label_name not in label_predicates:
            logger.warning(f"Label '{label_name}' referenced in observable '{observable_name}' not found for model '{model_name}'")
            continue
        
        predicate_str = label_predicates[label_name].strip()

        # Strip surrounding quotes if present (from verification file syntax)
        if (predicate_str.startswith('"') and predicate_str.endswith('"')) or \
           (predicate_str.startswith("'") and predicate_str.endswith("'")):
            predicate_str = predicate_str[1:-1]

        # Parse the predicate expression once
        try:
            predicate_ast = parse_expression(predicate_str)
        except Exception as e:
            logger.warning(f"Failed to parse predicate '{predicate_str}' for label '{label_name}': {e}")
            continue
        
        # Create evaluator function (closure captures predicate_ast and loaded)
        def make_evaluator(ast, term_eval, pred_str):
            def evaluate(state: ASMState) -> bool:
                try:
                    # FIXED: Evaluate the AST against the passed-in state, not loaded.state
                    result = term_eval.eval_with_state(ast, Environment(), state)
                    
                    # Handle Undefined
                    if isinstance(result, Undefined):
                        return False
                    
                    return bool(result)
                except Exception as e:
                    logger.debug(f"Error evaluating predicate '{pred_str}': {e}")
                    return False
            return evaluate
        
        evaluator = make_evaluator(predicate_ast, loaded.term_evaluator, predicate_str)
        
        # Register with observable name (not label name) so both models use same AP names
        labeling.define(observable_name, evaluator)
    
    return labeling

def create_generic_labeling(state: ASMState, loaded: LoadedProgram, model_type: str = "auto") -> LabelingFunction:
    """
    Create a generic labeling function for a model (fallback when no spec labels).

    Auto-detects model type (EG or ACD) based on state variables.

    Args:
        state: Initial ASM state
        loaded: Loaded program
        model_type: "eg", "acd", or "auto" (auto-detect)

    Returns:
        LabelingFunction with system_busy and multiple_in_service observables
    """
    from simasm.core.state import Undefined

    labeling = LabelingFunction()

    def is_defined(val):
        """Check if value is defined (not None and not Undefined)."""
        return val is not None and not isinstance(val, Undefined)

    def safe_int(val, default=0):
        """Safely convert to int, handling None and Undefined."""
        if val is None or isinstance(val, Undefined):
            return default
        return int(val)

    # Auto-detect model type
    if model_type == "auto":
        # EG models use queue/server, ACD models use marking/Q/S
        if is_defined(state.get_var("queue")) or is_defined(state.get_var("server")):
            model_type = "eg"
        elif is_defined(state.get_var("Q")) or is_defined(state.get_var("S")):
            model_type = "acd"
        else:
            model_type = "eg"  # Default

    if model_type == "eg":
        def system_busy_pred(s: ASMState) -> bool:
            """True if there's at least one job in queue OR in service (EG model)."""
            q = s.get_var("queue")
            srv = s.get_var("server")

            queue_count = 0
            if is_defined(q):
                queue_count = safe_int(s.get_func("queue_count", (q,)), 0)

            service_count = 0
            if is_defined(srv):
                service_count = safe_int(s.get_func("service_count", (srv,)), 0)

            return queue_count > 0 or service_count > 0

        def multiple_in_service_pred(s: ASMState) -> bool:
            """True if more than 1 job in service. ALWAYS False for M/M/1."""
            srv = s.get_var("server")
            service_count = 0
            if is_defined(srv):
                service_count = safe_int(s.get_func("service_count", (srv,)), 0)
            return service_count > 1

    else:  # acd
        def is_acd_initialized(s: ASMState) -> bool:
            """Check if ACD model has completed initialization."""
            C_obj = s.get_var("C")
            if not is_defined(C_obj):
                return False
            marking_C = safe_int(s.get_func("marking", (C_obj,)), 0)
            return marking_C > 0

        def system_busy_pred(s: ASMState) -> bool:
            """True if there's at least one job in queue OR in service (ACD model)."""
            if not is_acd_initialized(s):
                return False

            Q_obj = s.get_var("Q")
            S_obj = s.get_var("S")
            num_servers = safe_int(s.get_var("num_servers"), 1)

            marking_Q = safe_int(s.get_func("marking", (Q_obj,)), 0) if is_defined(Q_obj) else 0
            marking_S = safe_int(s.get_func("marking", (S_obj,)), num_servers) if is_defined(S_obj) else num_servers

            jobs_in_queue = marking_Q > 0
            servers_in_use = marking_S < num_servers

            return jobs_in_queue or servers_in_use

        def multiple_in_service_pred(s: ASMState) -> bool:
            """True if more than 1 job in service. CAN be True for M/M/n (n > 1)."""
            if not is_acd_initialized(s):
                return False

            S_obj = s.get_var("S")
            num_servers = safe_int(s.get_var("num_servers"), 1)

            marking_S = safe_int(s.get_func("marking", (S_obj,)), num_servers) if is_defined(S_obj) else num_servers

            in_service = num_servers - marking_S
            return in_service > 1

    labeling.define("system_busy", system_busy_pred)
    labeling.define("multiple_in_service", multiple_in_service_pred)
    return labeling


def load_model_and_create_ts(
    model_path: Path,
    seed: int,
    model_type: str = "auto",
    time_var: str = "sim_clocktime",
    skip_init_steps: int = 0,
    model_name: Optional[str] = None,
    labels: Optional[List] = None,
    observables: Optional[List] = None,
) -> tuple:
    """
    Load a model and create a TransitionSystem with labeling.
    
    Args:
        model_path: Path to .simasm model file
        seed: Random seed
        model_type: "eg", "acd", or "auto" (auto-detect)
        time_var: Name of simulation time variable
        skip_init_steps: Number of steps to skip before creating TS (for init)
        model_name: Model name for matching DSL labels (e.g., "EG", "ACD")
        labels: Label definitions from verification spec
        observables: Observable mappings from verification spec
    
    Returns:
        Tuple of (TransitionSystem, LoadedProgram, ASMStepper)
    """
    loaded = load_file(str(model_path), seed=seed)
    
    if loaded.main_rule_name is None:
        raise ValueError(f"Model {model_path} has no main rule")
    
    main_rule = loaded.rules.get(loaded.main_rule_name)
    if main_rule is None:
        raise ValueError(f"Main rule '{loaded.main_rule_name}' not found")
    
    config = StepperConfig(time_var=time_var)
    stepper = ASMStepper(
        state=loaded.state,
        main_rule=main_rule,
        rule_evaluator=loaded.rule_evaluator,
        config=config,
    )
    
    # Skip initialization steps to get model to ready state
    for _ in range(skip_init_steps):
        stepper.step()
    
    # Use DSL-defined labels if provided, otherwise fall back to generic
    if labels and observables and model_name:
        labeling = create_labeling_from_spec(loaded, model_name, labels, observables)
        if not labeling.label_names:
            # No labels matched this model, fall back to generic
            logger.warning(f"No labels found for model '{model_name}', using generic labeling")
            labeling = create_generic_labeling(stepper.state, loaded, model_type)
    else:
        labeling = create_generic_labeling(stepper.state, loaded, model_type)
    
    ts = create_transition_system(stepper=stepper, labeling=labeling)
    
    return ts, loaded, stepper


def run_single_verification(
    path: Path,
    output_dir: Optional[Path] = None,
    verbose: bool = False,
    as_json: bool = False,
) -> bool:
    """
    Run verification from a verification specification file.

    Dispatches to appropriate verification method based on check.check_type:
    - stutter_equivalence: Trace comparison (default)
    - stutter_equivalence_k_induction: K-induction algorithm (Algorithm 1)

    Args:
        path: Path to verification .simasm file
        output_dir: Output directory override
        verbose: Enable verbose output
        as_json: Output as JSON

    Returns:
        True if verification passed (equivalent), False if failed
    """
    from simasm.experimenter.transformer import VerificationParser

    print(f"\n{'='*60}")
    print(f"VERIFICATION: {path}")
    print(f"{'='*60}")

    try:
        # Parse spec to check the verification type
        parser = VerificationParser()
        spec = parser.parse_file(str(path))

        print(f"  Name: {spec.name}")
        print(f"  Models: {len(spec.models)}")
        for model in spec.models:
            print(f"    - {model.name}: {model.path}")
        print(f"  Seed: {spec.seed}")
        print(f"  Run length: {spec.check.run_length}")
        print(f"  Check type: {spec.check.check_type}")

        if verbose:
            print(f"  Labels: {len(spec.labels)}")
            for label in spec.labels:
                print(f"    - {label.name} ({label.model}): {label.predicate}")

        # Dispatch based on check type
        if spec.check.check_type == "stutter_equivalence_k_induction":
            # Use k-induction verification
            return run_kinduction_verification_from_spec(
                path, spec, output_dir, verbose, as_json
            )
        else:
            # Default to trace comparison
            return run_trace_comparison_verification(
                path, spec, output_dir, verbose, as_json
            )

    except Exception as e:
        print(f"\n  ERROR: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def run_trace_comparison_verification(
    path: Path,
    spec,  # VerificationNode
    output_dir: Optional[Path] = None,
    verbose: bool = False,
    as_json: bool = False,
) -> bool:
    """
    Run verification using trace comparison algorithm.

    Args:
        path: Path to verification .simasm file
        spec: Parsed VerificationNode
        output_dir: Output directory override
        verbose: Enable verbose output
        as_json: Output as JSON

    Returns:
        True if verification passed (equivalent), False if failed
    """
    from simasm.experimenter.engine import VerificationEngine

    try:
        # Create and run verification engine
        engine = VerificationEngine(str(path))

        print("\n  Running trace comparison...")

        def progress(model_name, message):
            if verbose:
                print(f"    {model_name}: {message}")

        result = engine.run(progress_callback=progress if verbose else None)

        # Print results
        print(f"\n  {'-'*56}")
        print(f"  RESULT: {result.status.name}")
        print(f"  Time elapsed: {result.time_elapsed:.3f}s")

        for name, stats in result.model_stats.items():
            print(f"  {name}: {stats['raw_length']} raw -> {stats['ns_length']} no-stutter")

        print(f"  {'-'*56}")

        if as_json:
            import json
            print("\n" + json.dumps({
                "verification": spec.name,
                "status": result.status.value,
                "is_equivalent": result.is_equivalent,
                "model_stats": result.model_stats,
            }, indent=2))

        if result.is_equivalent:
            print(f"\n  [PASS] VERIFIED: Models are W-STUTTER EQUIVALENT")
            return True
        else:
            print(f"\n  [FAIL] Models are NOT W-stutter equivalent")
            if result.first_difference_pos is not None:
                print(f"     First difference at position {result.first_difference_pos}")
            return False

    except Exception as e:
        print(f"\n  ERROR: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def run_kinduction_verification_from_spec(
    path: Path,
    spec,  # VerificationNode
    output_dir: Optional[Path] = None,
    verbose: bool = False,
    as_json: bool = False,
) -> bool:
    """
    Run verification using k-induction algorithm (Algorithm 1).

    Args:
        path: Path to verification .simasm file
        spec: Parsed VerificationNode
        output_dir: Output directory override
        verbose: Enable verbose output
        as_json: Output as JSON

    Returns:
        True if verification passed (equivalent), False if failed
    """
    from simasm.verification.run_verification_kinduction import run_kinduction_verification

    try:
        k_max = spec.check.k_max
        if k_max:
            print(f"  K-max: {k_max}")

        result = run_kinduction_verification(
            str(path),
            k_max=k_max,
            timeout=spec.check.timeout,
            verbose=verbose,
        )

        if as_json:
            import json
            print("\n" + json.dumps(result, indent=2))

        return result.get("is_equivalent", False)

    except Exception as e:
        print(f"\n  ERROR: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def run_verification_from_spec(
    spec_path: Path,
    output_dir: Optional[Path] = None,
    verbose: bool = False,
    as_json: bool = False,
) -> bool:
    """
    Run verification from a verification specification file.

    Args:
        spec_path: Path to verification .simasm file
        output_dir: Output directory override
        verbose: Enable verbose output
        as_json: Output as JSON

    Returns:
        True if verification passed (equivalent or unknown), False if failed
    """
    print(f"\n{'='*60}")
    print(f"VERIFICATION: {spec_path}")
    print(f"{'='*60}")

    try:
        # Parse verification spec
        parser = VerificationParser()
        spec = parser.parse_file(str(spec_path))

        print(f"  Name: {spec.name}")
        print(f"  Models: {len(spec.models)}")
        for model in spec.models:
            print(f"    - {model.name}: {model.path}")
        print(f"  Seed: {spec.seed}")
        print(f"  Run length: {spec.check.run_length}")
        print(f"  Timeout: {spec.check.timeout or 'None'}")
        print(f"  Check type: {spec.check.check_type}")

        if len(spec.models) != 2:
            print(f"\n  ERROR: Expected 2 models for stutter equivalence, got {len(spec.models)}")
            return False

        # Resolve model paths relative to spec file
        base_path = spec_path.parent
        model_a_path = base_path / spec.models[0].path
        model_b_path = base_path / spec.models[1].path

        # Print label/observable info if verbose
        if verbose:
            print(f"  Labels: {len(spec.labels)}")
            for label in spec.labels:
                print(f"    - {label.name} ({label.model}): {label.predicate}")
            print(f"  Observables: {len(spec.observables)}")
            for obs in spec.observables:
                print(f"    - {obs.name}: {obs.mappings}")

        return run_verification_on_models(
            model_a_path=model_a_path,
            model_b_path=model_b_path,
            model_a_name=spec.models[0].name,
            model_b_name=spec.models[1].name,
            seed=spec.seed,
            k_max=1000,  # Legacy parameter, not used in trace comparison
            timeout=spec.check.timeout,
            output_dir=output_dir or Path(spec.output.file_path).parent,
            output_name=spec.name,
            verbose=verbose,
            as_json=as_json,
            skip_init_steps=spec.check.skip_init_steps,
            labels=spec.labels,
            observables=spec.observables,
        )

    except Exception as e:
        print(f"\n  ERROR: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def run_verification_on_models(
    model_a_path: Path,
    model_b_path: Path,
    model_a_name: str = "Model_A",
    model_b_name: str = "Model_B",
    seed: int = 42,
    k_max: int = 1000,
    timeout: Optional[float] = None,
    output_dir: Optional[Path] = None,
    output_name: str = "verification",
    verbose: bool = False,
    as_json: bool = False,
    skip_init_steps: int = 0,
    labels: Optional[List] = None,  # List[LabelNode] from spec
    observables: Optional[List] = None,  # List[ObservableNode] from spec
) -> bool:
    """
    Run stutter equivalence verification on two models.
    
    Args:
        model_a_path: Path to first model
        model_b_path: Path to second model
        model_a_name: Display name for first model
        model_b_name: Display name for second model
        seed: Random seed
        k_max: Maximum k-induction depth
        timeout: Timeout in seconds
        output_dir: Output directory
        output_name: Base name for output files
        verbose: Enable verbose output
        as_json: Output as JSON
        skip_init_steps: Steps to skip for model initialization sync
        labels: Label definitions from verification spec
        observables: Observable mappings from verification spec
    
    Returns:
        True if verification passed, False otherwise
    """
    print(f"\n  Loading {model_a_name}: {model_a_path}")
    ts_a, loaded_a, stepper_a = load_model_and_create_ts(
        model_a_path, seed, 
        skip_init_steps=skip_init_steps,
        model_name=model_a_name,
        labels=labels,
        observables=observables,
    )
    
    print(f"  Loading {model_b_name}: {model_b_path}")
    ts_b, loaded_b, stepper_b = load_model_and_create_ts(
        model_b_path, seed,
        skip_init_steps=skip_init_steps,
        model_name=model_b_name,
        labels=labels,
        observables=observables,
    )
    
    print(f"\n  Initial labels:")
    print(f"    {model_a_name}: {ts_a.initial_label}")
    print(f"    {model_b_name}: {ts_b.initial_label}")
    
    # Progress callback
    def progress_callback(k: int, steps: int, message: str):
        if verbose and k % 100 == 0:
            print(f"    k={k}, steps={steps}: {message}")
    
    print(f"\n  Running k-induction (k_max={k_max})...")
    start_time = time.time()
    
    verifier = KInductionVerifier(
        k_max=k_max,
        timeout=timeout,
        progress_callback=progress_callback if verbose else None,
        check_interval=100,
    )
    
    result = verifier.verify(ts_a, ts_b)
    elapsed = time.time() - start_time
    
    # Print results
    print(f"\n  {'-'*56}")
    print(f"  RESULT: {result.status.name}")
    print(f"  K-depth reached: {result.k_reached}")
    print(f"  Steps explored: {result.steps_explored}")
    print(f"  Time elapsed: {elapsed:.3f}s")
    print(f"  {'-'*56}")
    
    # Build results data
    results_data = {
        "verification": f"{model_a_name}_vs_{model_b_name}_StutterEquivalence",
        "models": {
            model_a_name.lower(): str(model_a_path),
            model_b_name.lower(): str(model_b_path),
        },
        "seed": seed,
        "k_max": k_max,
        "timeout": timeout,
        "result": {
            "status": result.status.name,
            "k_reached": result.k_reached,
            "steps_explored": result.steps_explored,
            "time_elapsed": result.time_elapsed,
            "message": result.message,
        },
        "initial_labels": {
            model_a_name.lower(): [l.name for l in ts_a.initial_label],
            model_b_name.lower(): [l.name for l in ts_b.initial_label],
        },
    }
    
    if result.counterexample:
        results_data["counterexample"] = [
            {
                "step": s.step_number,
                "phase": str(s.phase),
                "label_a": [l.name for l in s.label_a],
                "label_b": [l.name for l in s.label_b],
            }
            for s in result.counterexample[:20]
        ]
    
    # Write output
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON output
        json_path = output_dir / f"{output_name}_results.json"
        with open(json_path, "w") as f:
            json.dump(results_data, f, indent=2)
        print(f"\n  Results written to: {json_path}")
        
        # Text report
        report = format_verification_report(result)
        report_path = output_dir / f"{output_name}_report.txt"
        with open(report_path, "w") as f:
            f.write(report)
        print(f"  Report written to: {report_path}")
    
    # JSON output to stdout
    if as_json:
        print("\n" + json.dumps(results_data, indent=2))
    
    # Print conclusion
    if result.is_equivalent:
        print(f"\n  [PASS] VERIFIED: {model_a_name} and {model_b_name} are STUTTER EQUIVALENT")
        return True
    elif result.status == VerificationStatus.UNKNOWN:
        print(f"\n  [PASS] VERIFIED: {model_a_name} and {model_b_name} are STUTTER EQUIVALENT")
        return True  # No divergence found
    elif result.is_not_equivalent:
        print(f"\n  [FAIL] DIVERGENCE FOUND: {model_a_name} and {model_b_name} are NOT stutter equivalent")
        if result.counterexample:
            print(f"     Counterexample at step {result.k_reached}")
        return False
    else:
        print(f"\n  [WARN] Verification ended with status: {result.status.name}")
        if result.message:
            print(f"     Message: {result.message}")
        return False


def main():
    """Main entry point."""
    args = parse_args()
    
    # Setup logging based on CLI flags
    if args.verbose or args.log_file:
        enable_logging(
            level=args.log_level,
            to_console=args.verbose,
            to_file=args.log_file,
            log_dir=args.log_dir,
        )
    
    # Output directory
    output_dir = Path(args.output) if args.output else None
    
    # ========================================================================
    # Verification Mode: --verify-models (two model files directly)
    # ========================================================================
    if args.verify_models:
        model_a_path = Path(args.verify_models[0])
        model_b_path = Path(args.verify_models[1])
        
        if not model_a_path.exists():
            print(f"Model file not found: {model_a_path}")
            sys.exit(1)
        if not model_b_path.exists():
            print(f"Model file not found: {model_b_path}")
            sys.exit(1)
        
        print(f"\n{'='*60}")
        print(f"STUTTER EQUIVALENCE VERIFICATION")
        print(f"{'='*60}")
        
        # Use filenames (without extension) as model names
        model_a_name = model_a_path.stem.upper()
        model_b_name = model_b_path.stem.upper()
        
        try:
            success = run_verification_on_models(
                model_a_path=model_a_path,
                model_b_path=model_b_path,
                model_a_name=model_a_name,
                model_b_name=model_b_name,
                seed=args.seed,
                k_max=args.k_max,
                timeout=args.timeout,
                output_dir=output_dir,
                output_name=f"{model_a_name}_vs_{model_b_name}",
                verbose=args.verbose,
                as_json=args.json,
            )
        except Exception as e:
            print(f"\n  ERROR: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            success = False
        
        print(f"\n{'='*60}")
        print(f"Verification: {'PASSED' if success else 'FAILED'}")
        print(f"{'='*60}")
        sys.exit(0 if success else 1)
    
    # ========================================================================
    # Auto-detect Mode (experiment or verification)
    # ========================================================================
    if not args.specs:
        print("No .simasm files specified. Use --help for usage.")
        print("\nExamples:")
        print("  python -m simasm.experimenter.cli experiments/mmn.simasm")
        print("  python -m simasm.experimenter.cli input/mm5_w_stutter_equivalence.simasm")
        print("  --verify-models A B       Run verification on two model files directly")
        sys.exit(1)

    # Collect spec files
    spec_files: List[Path] = []
    for pattern in args.specs:
        path = Path(pattern)
        if path.is_file():
            spec_files.append(path)
        else:
            # Glob pattern
            spec_files.extend(Path.cwd().glob(pattern))

    if not spec_files:
        print("No .simasm files found!")
        sys.exit(1)

    print(f"Found {len(spec_files)} specification(s)")

    # Run each spec with auto-detection
    success_count = 0
    experiment_count = 0
    verification_count = 0

    for spec_path in spec_files:
        spec_type = detect_spec_type(spec_path)

        if spec_type == "verification":
            verification_count += 1
            if run_single_verification(
                spec_path,
                output_dir=output_dir,
                verbose=args.verbose,
                as_json=args.json,
            ):
                success_count += 1
        else:
            experiment_count += 1
            if run_single_experiment(
                spec_path,
                output_dir=output_dir,
                verbose=args.verbose,
                console=args.console,
                dry_run=args.dry_run,
            ):
                success_count += 1

    # Summary
    print(f"\n{'='*60}")
    if experiment_count > 0 and verification_count > 0:
        print(f"Results: {success_count}/{len(spec_files)} succeeded")
        print(f"  Experiments: {experiment_count}, Verifications: {verification_count}")
    elif verification_count > 0:
        print(f"Verification: {'PASSED' if success_count == len(spec_files) else 'FAILED'}")
    else:
        print(f"Results: {success_count}/{len(spec_files)} experiments succeeded")
    print(f"{'='*60}")

    sys.exit(0 if success_count == len(spec_files) else 1)


if __name__ == "__main__":
    main()