#!/usr/bin/env python3
"""
verification/run_verification_kinduction.py

Run W-stutter equivalence verification using k-induction (Algorithm 1).

This script:
1. Parses a verification .simasm file with check type: stutter_equivalence_k_induction
2. Loads both models with the same seed
3. Creates TransitionSystem wrappers with labeling functions
4. Constructs ProductTransitionSystem
5. Runs KInductionVerifier (Algorithm 1)
6. Outputs VerificationResult with status and counterexample if found

References:
- Algorithm 1 (K-Induction for Stutter Equivalence) in thesis
- Theorem 1 (Soundness of Product Construction)
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from simasm.parser.loader import load_file
from simasm.runtime.stepper import ASMStepper, StepperConfig
from simasm.experimenter.transformer import VerificationParser
from simasm.experimenter.ast import VerificationNode
from simasm.verification.ts import TransitionSystem, TransitionSystemConfig
from simasm.verification.product import ProductTransitionSystem
from simasm.verification.kinduction import (
    KInductionVerifier,
    VerificationResult,
    VerificationStatus,
    format_verification_report,
)
from simasm.verification.label import Label, LabelSet, LabelingFunction
from simasm.core.terms import Environment, LocationTerm


def load_verification_spec(spec_path: str) -> VerificationNode:
    """Load and parse a verification specification file."""
    parser = VerificationParser()
    return parser.parse_file(spec_path)


def create_labeling_function(term_evaluator, labels: list) -> LabelingFunction:
    """
    Create a LabelingFunction from label definitions.

    Args:
        term_evaluator: The model's term evaluator
        labels: List of LabelNode definitions

    Returns:
        LabelingFunction that evaluates the predicates
    """
    labeling = LabelingFunction()

    def make_evaluator(fn, te):
        """Factory function to properly capture the function name and evaluator."""
        def evaluate(state) -> bool:
            try:
                term = LocationTerm(func_name=fn, arguments=[])
                result = te.eval(term, Environment())
                return bool(result)
            except Exception as e:
                return False
        return evaluate

    for label_node in labels:
        predicate = label_node.predicate.strip()

        if predicate.endswith("()"):
            # It's a 0-ary derived function call like "busy_eq_0()"
            func_name = predicate[:-2]
            labeling.define(label_node.name, make_evaluator(func_name, term_evaluator))
        else:
            # For other predicates
            def evaluate(state) -> bool:
                return False
            labeling.define(label_node.name, evaluate)

    return labeling


def create_transition_system(
    model_path: str,
    model_name: str,
    label_nodes: list,
    seed: int,
    end_time: float
) -> Tuple[TransitionSystem, dict]:
    """
    Load a model and create a TransitionSystem wrapper.

    Args:
        model_path: Path to the .simasm model file
        model_name: Name of the model for logging
        label_nodes: List of LabelNode definitions for this model
        seed: Random seed
        end_time: Simulation end time

    Returns:
        tuple: (TransitionSystem, model_info dict)
    """
    print(f"  Loading {model_name} from {Path(model_path).name}...")

    # Load the model
    loaded = load_file(model_path, seed=seed)

    # Create labeling function with THIS model's term evaluator
    labeling = create_labeling_function(loaded.term_evaluator, label_nodes)

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

    # Create transition system with trace recording enabled
    ts_config = TransitionSystemConfig(
        max_stutter_depth=10000,  # High limit for long runs
        record_trace=False,  # Don't record trace (product system handles this)
        record_states=False,
    )
    ts = TransitionSystem(stepper, labeling, ts_config)

    model_info = {
        "name": model_name,
        "path": model_path,
        "initial_label": sorted(l.name for l in ts.initial_label),
    }

    print(f"    Initial label: {{{', '.join(model_info['initial_label'])}}}")

    return ts, model_info


def run_kinduction_verification(
    spec_path: str,
    k_max: Optional[int] = None,
    timeout: Optional[float] = None,
    end_time: Optional[float] = None,
    verbose: bool = True
) -> dict:
    """
    Run W-stutter equivalence verification using k-induction.

    Implements Algorithm 1 (K-Induction for Stutter Equivalence Verification).

    Args:
        spec_path: Path to verification .simasm file
        k_max: Override k_max from spec (or use spec's value)
        timeout: Override timeout from spec (or use spec's value)
        end_time: Override end_time from spec (or use spec's run_length)
        verbose: Whether to print detailed output

    Returns:
        dict with verification results
    """
    spec_file = Path(spec_path)
    base_path = spec_file.parent

    print("=" * 70)
    print("  K-INDUCTION STUTTER EQUIVALENCE VERIFICATION (Algorithm 1)")
    print("=" * 70)

    # Parse specification
    print(f"\nLoading specification: {spec_file.name}")
    spec = load_verification_spec(spec_path)
    print(f"  Verification: {spec.name}")
    print(f"  Seed: {spec.seed}")
    print(f"  Models: {[m.name for m in spec.models]}")
    print(f"  Labels defined: {len(spec.labels)}")

    # Get k_max, timeout, end_time from spec or args
    effective_k_max = k_max if k_max is not None else (spec.check.k_max or 10000)
    effective_timeout = timeout if timeout is not None else spec.check.timeout
    effective_end_time = end_time if end_time is not None else spec.check.run_length

    print(f"\nVerification parameters:")
    print(f"  k_max: {effective_k_max}")
    print(f"  timeout: {effective_timeout}s" if effective_timeout else "  timeout: None")
    print(f"  run_length: {effective_end_time}")

    if len(spec.models) != 2:
        raise ValueError(f"Expected exactly 2 models, got {len(spec.models)}")

    # Create transition systems for both models
    print(f"\nCreating transition systems...")
    transition_systems = {}
    model_infos = {}

    for model_import in spec.models:
        model_path = base_path / model_import.path

        # Get labels for this model
        model_labels = [l for l in spec.labels if l.model == model_import.name]

        # Create transition system
        ts, info = create_transition_system(
            str(model_path),
            model_import.name,
            model_labels,
            spec.seed,
            effective_end_time
        )

        transition_systems[model_import.name] = ts
        model_infos[model_import.name] = info

    # Get the two model names and transition systems
    model_names = list(transition_systems.keys())
    name_a, name_b = model_names[0], model_names[1]
    ts_a, ts_b = transition_systems[name_a], transition_systems[name_b]

    # Verify Assumption 1: Initial state correspondence
    if ts_a.initial_label != ts_b.initial_label:
        print(f"\n  ERROR: Assumption 1 violation!")
        print(f"  Initial labels don't match:")
        print(f"    {name_a}: {{{', '.join(sorted(l.name for l in ts_a.initial_label))}}}")
        print(f"    {name_b}: {{{', '.join(sorted(l.name for l in ts_b.initial_label))}}}")

        return {
            "verification": spec.name,
            "seed": spec.seed,
            "k_max": effective_k_max,
            "status": "ASSUMPTION_VIOLATED",
            "is_equivalent": False,
            "message": "Assumption 1 violation: Initial labels don't match",
        }

    # Create k-induction verifier
    print(f"\nRunning k-induction verification (Algorithm 1)...")

    def progress_callback(k: int, steps: int, message: str):
        if verbose and k % 100 == 0:
            print(f"    k={k}, steps={steps}: {message}")

    verifier = KInductionVerifier(
        k_max=effective_k_max,
        timeout=effective_timeout,
        progress_callback=progress_callback if verbose else None,
        check_interval=100,
    )

    # Run verification
    start_time = time.time()
    result = verifier.verify(ts_a, ts_b)
    elapsed = time.time() - start_time

    # Print results
    print("\n" + "=" * 70)
    if result.is_equivalent:
        print("  RESULT: W-STUTTER EQUIVALENT (Verified by K-Induction)")
        print(f"  The {name_a} and {name_b} models produce equivalent observable behavior!")
    elif result.is_not_equivalent:
        print("  RESULT: NOT W-STUTTER EQUIVALENT")
        print(f"  The {name_a} and {name_b} models diverge at step {result.k_reached}.")
        if result.counterexample:
            print(f"  Counterexample length: {len(result.counterexample)}")
    elif result.is_timeout:
        print("  RESULT: TIMEOUT")
        print(f"  Verification timed out after {result.time_elapsed:.1f}s")
    else:
        print("  RESULT: UNKNOWN")
        print(f"  Reached k_max={result.k_reached} without conclusion")
    print("=" * 70)

    print(f"\nVerification statistics:")
    print(f"  K-depth reached: {result.k_reached}")
    print(f"  Steps explored: {result.steps_explored}")
    print(f"  Time elapsed: {result.time_elapsed:.3f}s")

    # Build result dict
    result_dict = {
        "verification": spec.name,
        "algorithm": "k-induction",
        "seed": spec.seed,
        "k_max": effective_k_max,
        "run_length": effective_end_time,
        "timeout": effective_timeout,
        "models": {
            name_a: model_infos[name_a],
            name_b: model_infos[name_b],
        },
        "status": result.status.name,
        "is_equivalent": result.is_equivalent,
        "k_reached": result.k_reached,
        "steps_explored": result.steps_explored,
        "time_elapsed": result.time_elapsed,
        "message": result.message,
    }

    # Add counterexample if present and requested
    if result.counterexample and spec.output.include_counterexample:
        result_dict["counterexample"] = {
            "length": len(result.counterexample),
            "path": [
                {
                    "step": state.step_number,
                    "label_a": sorted(l.name for l in state.label_a),
                    "label_b": sorted(l.name for l in state.label_b),
                    "phase": str(state.phase),
                }
                for state in result.counterexample[:20]  # Limit to first 20 states
            ]
        }

    # Write output if specified
    if spec.output.file_path:
        output_path = base_path / spec.output.file_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine format
        if spec.output.format.lower() == "json" or output_path.suffix == ".json":
            with open(output_path, "w") as f:
                json.dump(result_dict, f, indent=2)
        elif spec.output.format.lower() == "csv" or output_path.suffix == ".csv":
            # Write CSV summary
            import csv
            with open(output_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["verification", "algorithm", "status", "k_reached", "steps", "time_s"])
                writer.writerow([
                    spec.name,
                    "k-induction",
                    result.status.name,
                    result.k_reached,
                    result.steps_explored,
                    f"{result.time_elapsed:.3f}"
                ])
        else:
            # Default to JSON
            with open(output_path, "w") as f:
                json.dump(result_dict, f, indent=2)

        print(f"\nResults written to: {output_path}")

    return result_dict


def main():
    """Command-line entry point."""
    if len(sys.argv) < 2:
        print("Usage: python run_verification_kinduction.py <verification.simasm> [k_max] [timeout]")
        print("\nExample:")
        print("  python run_verification_kinduction.py test/input/experiments/mm5_w_stutter_equivalence_kinduction.simasm")
        print("  python run_verification_kinduction.py verification.simasm 10000 600")
        sys.exit(1)

    spec_path = sys.argv[1]
    k_max = int(sys.argv[2]) if len(sys.argv) > 2 else None
    timeout = float(sys.argv[3]) if len(sys.argv) > 3 else None

    result = run_kinduction_verification(
        spec_path,
        k_max=k_max,
        timeout=timeout,
    )

    sys.exit(0 if result["is_equivalent"] else 1)


if __name__ == "__main__":
    main()
