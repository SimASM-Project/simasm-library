"""
simasm/api.py

Python API for SimASM - use SimASM without cell magics.

This module provides a clean Python API for defining models, running experiments,
and verifying model equivalence using Python strings instead of cell magics.

This avoids Colab/IDE linter issues with DSL syntax.

Usage:
    import simasm

    # Define models as Python strings (no linter warnings!)
    eg_model = '''
    domain Object
    domain Load <: Object
    ...
    '''

    # Register models
    simasm.register_model("mm1_eg", eg_model)
    simasm.register_model("mm1_acd", acd_model)

    # Run experiments
    result = simasm.run_experiment('''
    experiment Test:
        model := "mm1_eg"
        replication:
            count: 10
            ...
        endreplication
        ...
    endexperiment
    ''')

    # Run verifications
    result = simasm.verify('''
    verification Check:
        models:
            import EG from "mm1_eg"
            import ACD from "mm1_acd"
        endmodels
        ...
    endverification
    ''')
"""

import tempfile
from pathlib import Path
from typing import Dict, Optional, Any, Union

# Global model registry (shared with magic.py)
_model_registry: Dict[str, str] = {}
_temp_dir: Optional[str] = None


def _get_temp_dir() -> str:
    """Get or create the temporary directory for model files."""
    global _temp_dir
    if _temp_dir is None:
        _temp_dir = tempfile.mkdtemp(prefix="simasm_api_")
    return _temp_dir


# =============================================================================
# Model Registry Functions
# =============================================================================

def register_model(name: str, source: str) -> None:
    """
    Register a SimASM model from source code.

    The model can later be referenced by name in experiments and verifications.

    Args:
        name: Name to register the model under
        source: SimASM source code as a string

    Example:
        simasm.register_model("mm1_queue", '''
        domain Object
        domain Load <: Object

        const queue: Queue
        var queue_length: Nat

        init:
            queue_length := 0
        endinit

        main rule main =
            queue_length := queue_length + 1
        endrule
        ''')
    """
    _model_registry[name] = source


def get_model(name: str) -> Optional[str]:
    """
    Get a registered model's source code.

    Args:
        name: Name of the model

    Returns:
        Model source code, or None if not found
    """
    return _model_registry.get(name)


def list_models() -> list:
    """
    List all registered model names.

    Returns:
        List of model names
    """
    return list(_model_registry.keys())


def clear_models() -> None:
    """Clear all registered models."""
    _model_registry.clear()


def unregister_model(name: str) -> bool:
    """
    Remove a model from the registry.

    Args:
        name: Name of the model to remove

    Returns:
        True if model was removed, False if not found
    """
    if name in _model_registry:
        del _model_registry[name]
        return True
    return False


# =============================================================================
# Experiment Functions
# =============================================================================

def run_experiment(spec: str, progress: bool = True) -> Any:
    """
    Run an experiment from a specification string.

    Models referenced in the experiment should be pre-registered using
    register_model(), or be file paths.

    Args:
        spec: Experiment specification as a SimASM string
        progress: Whether to show progress during execution

    Returns:
        ExperimentResult with all replication results and summary

    Example:
        result = simasm.run_experiment('''
        experiment LittlesLaw:
            model := "mm1_eg"

            replication:
                count: 10
                warm_up_time: 100.0
                run_length: 1000.0
                seed_strategy: "incremental"
                base_seed: 12345
            endreplication

            statistics:
                stat L_queue: time_average
                    expression: "lib.length(queues(queue))"
                endstat
            endstatistics

            output:
                format: "json"
                file_path: "results.json"
            endoutput
        endexperiment
        ''')

        print(f"Mean queue length: {result.summary['L_queue'].mean:.3f}")
    """
    from simasm.experimenter.transformer import ExperimentParser
    from simasm.experimenter.engine import ExperimenterEngine

    # Parse the specification
    parser = ExperimentParser()
    parsed = parser.parse(spec)

    # Check if model is in registry
    model_path = parsed.model_path
    if model_path in _model_registry:
        # Write model to temp file
        temp_dir = Path(_get_temp_dir())
        model_source = _model_registry[model_path]
        model_file = temp_dir / f"{model_path}.simasm"
        model_file.write_text(model_source, encoding='utf-8')
        parsed.model_path = str(model_file)
        base_path = temp_dir
    else:
        base_path = Path.cwd()

    # Run the experiment
    engine = ExperimenterEngine(parsed, base_path=base_path)

    def progress_callback(rep_id, total):
        if progress:
            print(f"  Replication {rep_id}/{total}...", end='\r')

    result = engine.run(progress_callback=progress_callback if progress else None)

    if progress:
        print()  # Clear progress line

    return result


# =============================================================================
# Verification Functions
# =============================================================================

def verify(spec: str, progress: bool = True) -> Any:
    """
    Run a verification from a specification string.

    Models referenced in the verification should be pre-registered using
    register_model(), or be file paths.

    Dispatches to appropriate verification method based on check.check_type:
    - stutter_equivalence: Trace comparison (default)
    - stutter_equivalence_k_induction: K-induction algorithm (Algorithm 1)

    Args:
        spec: Verification specification as a SimASM string
        progress: Whether to show progress during execution

    Returns:
        TraceVerificationResult or dict with equivalence status and details

    Example:
        result = simasm.verify('''
        verification EG_vs_ACD:
            models:
                import EG from "mm1_eg"
                import ACD from "mm1_acd"
            endmodels

            seed: 42

            labels:
                label busy_eq_0 for EG: "busy_eq_0()"
                label busy_eq_0 for ACD: "busy_eq_0()"
            endlabels

            observables:
                observable busy_eq_0:
                    EG -> busy_eq_0
                    ACD -> busy_eq_0
                endobservable
            endobservables

            check:
                type: stutter_equivalence
                run_length: 1000.0
            endcheck

            output:
                format: "csv"
                file_path: "results.csv"
            endoutput
        endverification
        ''')

        if result.is_equivalent:
            print("Models are W-stutter equivalent!")
        else:
            print(f"First difference at position {result.first_difference_pos}")
    """
    from simasm.experimenter.transformer import VerificationParser

    # Parse the specification
    parser = VerificationParser()
    parsed = parser.parse(spec)

    # Check if models are in registry and write them to temp files
    temp_dir = Path(_get_temp_dir())
    for model_import in parsed.models:
        if model_import.path in _model_registry:
            model_source = _model_registry[model_import.path]
            model_file = temp_dir / f"{model_import.path}.simasm"
            model_file.write_text(model_source, encoding='utf-8')
            model_import.path = str(model_file)

    # Dispatch based on check type
    if parsed.check.check_type == "stutter_equivalence_k_induction":
        # Use k-induction verification
        return _run_kinduction_verification(parsed, temp_dir, progress)
    else:
        # Default to trace comparison
        return _run_trace_comparison_verification(parsed, temp_dir, progress)


def _run_trace_comparison_verification(parsed, base_path: Path, progress: bool) -> Any:
    """Run verification using trace comparison algorithm."""
    from simasm.experimenter.engine import VerificationEngine

    engine = VerificationEngine(parsed, base_path=base_path)

    def progress_callback(model_name, message):
        if progress:
            print(f"  {model_name}: {message}")

    result = engine.run(progress_callback=progress_callback if progress else None)
    return result


def _run_kinduction_verification(parsed, base_path: Path, progress: bool) -> Any:
    """Run verification using k-induction algorithm (Algorithm 1)."""
    from simasm.verification.run_verification_kinduction import (
        create_transition_system,
        KInductionVerifier,
    )
    from simasm.verification.kinduction import VerificationResult

    # Create transition systems for both models
    if len(parsed.models) != 2:
        raise ValueError(f"Expected 2 models, got {len(parsed.models)}")

    transition_systems = {}
    for model_import in parsed.models:
        model_path = base_path / model_import.path
        if not model_path.exists():
            model_path = Path(model_import.path)

        # Get labels for this model
        model_labels = [l for l in parsed.labels if l.model == model_import.name]

        ts, _ = create_transition_system(
            str(model_path),
            model_import.name,
            model_labels,
            parsed.seed,
            parsed.check.run_length
        )
        transition_systems[model_import.name] = ts

    # Get the two transition systems
    model_names = list(transition_systems.keys())
    ts_a, ts_b = transition_systems[model_names[0]], transition_systems[model_names[1]]

    # Create and run verifier
    k_max = parsed.check.k_max or 10000

    def progress_callback(k: int, steps: int, message: str):
        if progress and k % 100 == 0:
            print(f"  k={k}, steps={steps}: {message}")

    verifier = KInductionVerifier(
        k_max=k_max,
        timeout=parsed.check.timeout,
        progress_callback=progress_callback if progress else None,
        check_interval=100,
    )

    result = verifier.verify(ts_a, ts_b)

    # Return result dict for API consistency
    return {
        "verification": parsed.name,
        "algorithm": "k-induction",
        "status": result.status.name,
        "is_equivalent": result.is_equivalent,
        "k_reached": result.k_reached,
        "steps_explored": result.steps_explored,
        "time_elapsed": result.time_elapsed,
        "message": result.message,
    }


# =============================================================================
# Direct Execution Functions (without registration)
# =============================================================================

def run_model(
    source: str,
    steps: int = 1000,
    end_time: Optional[float] = None,
    seed: int = 42,
    time_var: str = "sim_clocktime",
) -> Any:
    """
    Run a SimASM model directly from source code.

    This is useful for quick experiments without setting up a full
    experiment specification.

    Args:
        source: SimASM model source code
        steps: Maximum number of steps (if end_time not specified)
        end_time: Simulation end time (overrides steps)
        seed: Random seed
        time_var: Name of the simulation clock variable

    Returns:
        Dict with final state information

    Example:
        result = simasm.run_model('''
        domain Object
        var counter: Nat
        var sim_clocktime: Real

        init:
            counter := 0
            sim_clocktime := 0.0
        endinit

        main rule main =
            counter := counter + 1
            sim_clocktime := sim_clocktime + 1.0
        endrule
        ''', end_time=100.0)

        print(f"Final counter: {result['counter']}")
    """
    from simasm.parser import load_string
    from simasm.runtime.stepper import ASMStepper, StepperConfig

    # Load the model
    loaded = load_string(source, seed=seed)

    # Get main rule
    main_rule = loaded.rules.get(loaded.main_rule_name)
    if main_rule is None:
        raise ValueError("Model has no main rule")

    # Create stepper
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
    if end_time is not None:
        stepper.run_until(end_time)
    else:
        for _ in range(steps):
            if not stepper.step():
                break

    # Collect final state
    result = {
        "step_count": stepper.step_count,
        "sim_time": stepper.sim_time,
    }

    # Add all variables to result (access private _variables dict)
    for name in loaded.state._variables:
        try:
            result[name] = loaded.state.get_var(name)
        except Exception:
            pass

    return result


def parse_model(source: str) -> Any:
    """
    Parse a SimASM model and return the AST.

    Useful for debugging and model validation.

    Args:
        source: SimASM model source code

    Returns:
        Parsed AST (ProgramNode)

    Example:
        ast = simasm.parse_model('''
        domain Object
        var x: Nat
        ''')
        print(ast.domains)
    """
    from simasm.parser import SimASMParser

    parser = SimASMParser()
    return parser.parse(source)


# =============================================================================
# Result Display Functions (for notebooks)
# =============================================================================

def display_experiment_result(result: Any) -> None:
    """
    Display experiment results in a formatted way.

    Works in both Jupyter notebooks and regular Python.

    Args:
        result: ExperimentResult to display
    """
    try:
        from IPython.display import display, HTML

        # Build HTML table
        html = ['<div style="margin: 10px 0;">']
        html.append('<h4>Experiment Results</h4>')
        html.append(f'<p><strong>Replications:</strong> {len(result.replications)}</p>')
        html.append(f'<p><strong>Total time:</strong> {result.total_wall_time:.2f}s</p>')

        if result.summary:
            html.append('<table style="border-collapse: collapse; margin: 10px 0;">')
            html.append('<tr style="background: #f0f0f0;">')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">Statistic</th>')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">Mean</th>')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">Std Dev</th>')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">95% CI</th>')
            html.append('</tr>')

            for name, stats in result.summary.items():
                html.append('<tr>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{name}</td>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{stats.mean:.4f}</td>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{stats.std_dev:.4f}</td>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">[{stats.ci_lower:.4f}, {stats.ci_upper:.4f}]</td>')
                html.append('</tr>')

            html.append('</table>')

        html.append('</div>')
        display(HTML('\n'.join(html)))

    except ImportError:
        # Fallback to text display
        print("=" * 60)
        print("EXPERIMENT RESULTS")
        print("=" * 60)
        print(f"Replications: {len(result.replications)}")
        print(f"Total time: {result.total_wall_time:.2f}s")
        print()

        if result.summary:
            print(f"{'Statistic':<25} {'Mean':>12} {'Std Dev':>12} {'95% CI':>25}")
            print("-" * 60)
            for name, stats in result.summary.items():
                ci = f"[{stats.ci_lower:.4f}, {stats.ci_upper:.4f}]"
                print(f"{name:<25} {stats.mean:>12.4f} {stats.std_dev:>12.4f} {ci:>25}")


# =============================================================================
# Conversion Functions
# =============================================================================

def convert_model(
    source: str,
    formalism: str = "event_graph",
    register_as: Optional[str] = None,
    output_file: Optional[str] = None,
) -> str:
    """
    Convert a JSON specification to SimASM code.

    Supports Event Graph and ACD formalisms.

    Args:
        source: Path to JSON file or JSON string
        formalism: "event_graph" or "acd"
        register_as: Optional model name to register
        output_file: Optional file path to write generated code

    Returns:
        Generated SimASM code as a string

    Example:
        # From file
        code = simasm.convert_model(
            "mm5_eg.json",
            formalism="event_graph",
            register_as="mm5_eg"
        )

        # Or from JSON string
        code = simasm.convert_model(
            '{"name": "example", "events": [...]}',
            formalism="event_graph"
        )
    """
    import json
    from pathlib import Path

    # Determine if source is a file path or JSON string
    source_path = Path(source)
    if source_path.exists():
        with open(source_path, "r") as f:
            json_data = json.load(f)
    else:
        # Assume it's a JSON string
        json_data = json.loads(source)

    # Convert based on formalism
    if formalism == "event_graph":
        from simasm.converter.event_graph.schema import EventGraphSpec
        from simasm.converter.event_graph.converter import convert_eg

        spec = EventGraphSpec.from_dict(json_data)
        simasm_code = convert_eg(spec)

    elif formalism == "acd":
        from simasm.converter.acd.schema import ACDSpec
        from simasm.converter.acd.converter import convert_acd

        spec = ACDSpec.from_dict(json_data)
        simasm_code = convert_acd(spec)

    else:
        raise ValueError(f"Unsupported formalism: {formalism}. Use 'event_graph' or 'acd'.")

    # Register if requested
    if register_as:
        register_model(register_as, simasm_code)

    # Write to file if requested
    if output_file:
        with open(output_file, "w") as f:
            f.write(simasm_code)

    return simasm_code


def display_verification_result(result: Any) -> None:
    """
    Display verification results in a formatted way.

    Works in both Jupyter notebooks and regular Python.

    Args:
        result: TraceVerificationResult to display
    """
    try:
        from IPython.display import display, HTML

        # Determine status color
        if result.is_equivalent:
            status_color = "#28a745"
            status_text = "EQUIVALENT"
            status_icon = "&#10004;"
        else:
            status_color = "#dc3545"
            status_text = "NOT EQUIVALENT"
            status_icon = "&#10008;"

        html = ['<div style="margin: 10px 0;">']
        html.append('<h4>Verification Results</h4>')
        html.append(f'<p style="font-size: 1.2em;">')
        html.append(f'<span style="background: {status_color}; color: white; padding: 4px 12px; border-radius: 4px; font-weight: bold;">')
        html.append(f'{status_icon} {status_text}')
        html.append('</span>')
        html.append('</p>')
        html.append(f'<p><strong>Time elapsed:</strong> {result.time_elapsed:.3f}s</p>')
        html.append(f'<p>{result.message}</p>')

        if result.model_stats:
            html.append('<table style="border-collapse: collapse; margin: 10px 0;">')
            html.append('<tr style="background: #f0f0f0;">')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">Model</th>')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">Raw Trace</th>')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">No-Stutter</th>')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">Stutter Steps</th>')
            html.append('</tr>')

            for name, stats in result.model_stats.items():
                html.append('<tr>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{name}</td>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{stats.get("raw_length", "?")}</td>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{stats.get("ns_length", "?")}</td>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{stats.get("stutter_steps", "?")}</td>')
                html.append('</tr>')

            html.append('</table>')

        html.append('</div>')
        display(HTML('\n'.join(html)))

    except ImportError:
        # Fallback to text display
        print("=" * 60)
        print("VERIFICATION RESULTS")
        print("=" * 60)

        if result.is_equivalent:
            print("[PASS] EQUIVALENT")
        else:
            print("[FAIL] NOT EQUIVALENT")

        print(f"Time elapsed: {result.time_elapsed:.3f}s")
        print(result.message)
        print()

        if result.model_stats:
            print(f"{'Model':<20} {'Raw':>10} {'No-Stutter':>12} {'Stutter':>10}")
            print("-" * 60)
            for name, stats in result.model_stats.items():
                print(f"{name:<20} {stats.get('raw_length', '?'):>10} {stats.get('ns_length', '?'):>12} {stats.get('stutter_steps', '?'):>10}")
