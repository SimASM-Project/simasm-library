#!/usr/bin/env python3
"""
verification/run_verification.py

Run W-stutter equivalence verification from a .simasm verification specification.

This script:
1. Parses a verification .simasm file
2. Loads both models with the same seed
3. Runs them for a fixed simulation time
4. Collects traces using the defined labels
5. Verifies W-stutter equivalence
6. Outputs results
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from simasm.parser.loader import load_file
from simasm.runtime.stepper import ASMStepper, StepperConfig
from simasm.experimenter.transformer import VerificationParser
from simasm.experimenter.ast import VerificationNode
from simasm.verification.trace import (
    Trace, no_stutter_trace, traces_stutter_equivalent,
    count_stutter_steps
)
from simasm.verification.label import Label, LabelSet, LabelingFunction
from simasm.core.terms import Environment, LocationTerm
from simasm.simulation.collector import parse_expression
from simasm.core.state import Undefined


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
                return False
        return evaluate

    for label_node in labels:
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
            print(f"  Warning: Failed to parse predicate '{predicate}': {e}")
            # Define a fallback that always returns False
            labeling.define(label_node.name, lambda s: False)

    return labeling


def run_model_trace(
    model_path: str,
    model_name: str,
    label_nodes: list,
    seed: int,
    end_time: float
) -> Tuple[Trace, List[dict]]:
    """
    Run a model and collect its trace.

    Args:
        model_path: Path to the .simasm model file
        model_name: Name of the model for logging
        label_nodes: List of LabelNode definitions for this model
        seed: Random seed
        end_time: Simulation end time

    Returns:
        tuple: (Trace, raw_states list)
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

    # Collect trace
    trace = Trace()
    raw_states = []

    # Record initial state
    initial_labels = labeling.evaluate(loaded.state)
    initial_time = loaded.state.get_var("sim_clocktime") or 0.0
    trace.append(initial_labels)
    raw_states.append({
        "step": 0,
        "time": initial_time,
        "labels": sorted(l.name for l in initial_labels)
    })

    # Run and collect
    step = 0
    while stepper.can_step():
        stepper.step()
        step += 1

        labels = labeling.evaluate(loaded.state)
        sim_time = loaded.state.get_var("sim_clocktime") or 0.0

        trace.append(labels)
        raw_states.append({
            "step": step,
            "time": sim_time,
            "labels": sorted(l.name for l in labels)
        })

    print(f"    Completed: {step} steps, final time {sim_time:.4f}")
    return trace, raw_states


def run_single_seed_verification(
    spec,
    base_path: Path,
    seed: int,
    end_time: float,
    verbose: bool = False
) -> dict:
    """
    Run verification for a single seed.

    Args:
        spec: VerificationNode specification
        base_path: Base path for model files
        seed: Random seed to use
        end_time: Simulation end time
        verbose: Whether to print detailed output

    Returns:
        dict with single-seed verification results
    """
    model_traces = {}
    model_raw = {}

    for model_import in spec.models:
        model_path = base_path / model_import.path
        model_labels = [l for l in spec.labels if l.model == model_import.name]

        trace, raw = run_model_trace(
            str(model_path),
            model_import.name,
            model_labels,
            seed,
            end_time
        )

        model_traces[model_import.name] = trace
        model_raw[model_import.name] = raw

    model_names = list(model_traces.keys())
    name_a, name_b = model_names[0], model_names[1]
    trace_a, trace_b = model_traces[name_a], model_traces[name_b]

    ns_a = no_stutter_trace(trace_a)
    ns_b = no_stutter_trace(trace_b)

    are_equivalent = traces_stutter_equivalent(trace_a, trace_b)

    return {
        "seed": seed,
        "is_equivalent": are_equivalent,
        "models": {
            name_a: {
                "raw_trace_length": len(trace_a),
                "no_stutter_length": len(ns_a),
                "stutter_steps": count_stutter_steps(trace_a)
            },
            name_b: {
                "raw_trace_length": len(trace_b),
                "no_stutter_length": len(ns_b),
                "stutter_steps": count_stutter_steps(trace_b)
            }
        },
        "ns_trace_a": ns_a,
        "ns_trace_b": ns_b,
    }


def run_verification(spec_path: str, end_time: float = 10.0, verbose: bool = True):
    """
    Run stutter equivalence verification from a specification file.

    Supports multi-seed verification: runs all seeds and reports aggregate results.

    Args:
        spec_path: Path to verification .simasm file
        end_time: Simulation end time
        verbose: Whether to print detailed output

    Returns:
        dict with verification results
    """
    spec_file = Path(spec_path)
    base_path = spec_file.parent

    print("=" * 70)
    print(f"  STUTTER EQUIVALENCE VERIFICATION")
    print("=" * 70)

    # Parse specification
    print(f"\nLoading specification: {spec_file.name}")
    spec = load_verification_spec(spec_path)
    print(f"  Verification: {spec.name}")
    print(f"  Seeds: {spec.seeds} ({len(spec.seeds)} total)")
    print(f"  Models: {[m.name for m in spec.models]}")
    print(f"  Labels defined: {len(spec.labels)}")

    if len(spec.models) != 2:
        raise ValueError(f"Expected exactly 2 models, got {len(spec.models)}")

    # Run verification for each seed
    seed_results = []
    failed_seeds = []

    print(f"\nRunning verification for {len(spec.seeds)} seed(s) until time {end_time}...")

    for i, seed in enumerate(spec.seeds):
        print(f"\n  [{i+1}/{len(spec.seeds)}] Seed {seed}...", end="", flush=True)

        result = run_single_seed_verification(
            spec, base_path, seed, end_time, verbose=False
        )
        seed_results.append(result)

        if result["is_equivalent"]:
            print(" EQUIVALENT")
        else:
            print(" NOT EQUIVALENT")
            failed_seeds.append(seed)

    # Aggregate results
    model_names = list(seed_results[0]["models"].keys())
    name_a, name_b = model_names[0], model_names[1]

    all_equivalent = len(failed_seeds) == 0
    equivalent_count = len(spec.seeds) - len(failed_seeds)

    # Compute average trace statistics
    avg_stats = {
        name_a: {
            "avg_raw_trace_length": sum(r["models"][name_a]["raw_trace_length"] for r in seed_results) / len(seed_results),
            "avg_no_stutter_length": sum(r["models"][name_a]["no_stutter_length"] for r in seed_results) / len(seed_results),
            "avg_stutter_steps": sum(r["models"][name_a]["stutter_steps"] for r in seed_results) / len(seed_results),
        },
        name_b: {
            "avg_raw_trace_length": sum(r["models"][name_b]["raw_trace_length"] for r in seed_results) / len(seed_results),
            "avg_no_stutter_length": sum(r["models"][name_b]["no_stutter_length"] for r in seed_results) / len(seed_results),
            "avg_stutter_steps": sum(r["models"][name_b]["stutter_steps"] for r in seed_results) / len(seed_results),
        }
    }

    # Show detailed comparison for first seed if verbose
    if verbose and seed_results:
        first_result = seed_results[0]
        ns_a = first_result["ns_trace_a"]
        ns_b = first_result["ns_trace_b"]

        print(f"\nNo-stutter trace comparison for seed {spec.seeds[0]} (first 15 positions):")
        print("-" * 80)

        max_positions = min(len(ns_a), len(ns_b), 15)

        for i in range(max_positions):
            labels_a = sorted(l.name for l in ns_a[i])
            labels_b = sorted(l.name for l in ns_b[i])
            match = "MATCH" if ns_a[i] == ns_b[i] else "DIFFER"
            print(f"  {i:3d}: {name_a}={{{', '.join(labels_a)}}}")
            print(f"       {name_b}={{{', '.join(labels_b)}}} [{match}]")

        if max_positions < len(ns_a) or max_positions < len(ns_b):
            print(f"  ... ({max(len(ns_a), len(ns_b)) - max_positions} more positions)")

    # Final result
    print("\n" + "=" * 70)
    if all_equivalent:
        print(f"  RESULT: STUTTER EQUIVALENT")
        print(f"  All {len(spec.seeds)} seeds verified equivalent!")
        print(f"  The {name_a} and {name_b} models produce equivalent observable behavior.")
    else:
        print(f"  RESULT: NOT STUTTER EQUIVALENT")
        print(f"  {equivalent_count}/{len(spec.seeds)} seeds equivalent, {len(failed_seeds)} failed")
        print(f"  Failed seeds: {failed_seeds}")
    print("=" * 70)

    # Build result dict
    result = {
        "verification": spec.name,
        "seeds": spec.seeds,
        "num_seeds": len(spec.seeds),
        "end_time": end_time,
        "equivalent_count": equivalent_count,
        "failed_seeds": failed_seeds,
        "is_equivalent": all_equivalent,
        "status": "EQUIVALENT" if all_equivalent else "NOT_EQUIVALENT",
        "average_statistics": avg_stats,
        "per_seed_results": [
            {
                "seed": r["seed"],
                "is_equivalent": r["is_equivalent"],
                "models": r["models"]
            }
            for r in seed_results
        ]
    }

    # Write output if specified
    if spec.output.file_path:
        output_path = base_path / spec.output.file_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nResults written to: {output_path}")

    return result


def main():
    """Command-line entry point."""
    if len(sys.argv) < 2:
        print("Usage: python run_verification.py <verification.simasm> [end_time]")
        print("\nExample:")
        print("  python run_verification.py simasm/input/mm5_w_stutter_equivalence.simasm 10.0")
        sys.exit(1)

    spec_path = sys.argv[1]
    end_time = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0

    result = run_verification(spec_path, end_time=end_time)

    sys.exit(0 if result["is_equivalent"] else 1)


if __name__ == "__main__":
    main()
