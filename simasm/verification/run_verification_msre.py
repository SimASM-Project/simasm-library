#!/usr/bin/env python3
"""
verification/run_verification_msre.py

Run macro-step refinement equivalence (MSRE) verification from a .simasm spec.

This script:
1. Parses a verification .simasm file with check type macro_step_refinement
2. Loads both models with the same seed
3. Constructs transition systems with labeling functions
4. Runs MSRE verification (tick-boundary label comparison)
5. Outputs results
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from simasm.parser.loader import load_file
from simasm.runtime.stepper import ASMStepper, StepperConfig
from simasm.experimenter.transformer import VerificationParser
from simasm.experimenter.ast import VerificationNode
from simasm.verification.label import LabelingFunction
from simasm.verification.ts import TransitionSystem
from simasm.verification.msre import MacroStepRefinementVerifier, MSREResult
from simasm.verification.run_verification import (
    load_verification_spec,
    create_labeling_function,
    build_transition_system,
)


def run_single_seed_msre(
    spec: VerificationNode,
    base_path: Path,
    seed: int,
    end_time: float,
) -> dict:
    """Run MSRE verification for a single seed."""
    model_systems = {}
    for model_import in spec.models:
        model_path = base_path / model_import.path
        model_labels = [l for l in spec.labels if l.model == model_import.name]

        ts = build_transition_system(
            str(model_path),
            model_import.name,
            model_labels,
            seed,
            end_time,
        )
        model_systems[model_import.name] = ts

    model_names = list(model_systems.keys())
    name_a, name_b = model_names[0], model_names[1]
    ts_a, ts_b = model_systems[name_a], model_systems[name_b]

    max_boundaries = None
    if spec.check.k_max is not None:
        max_boundaries = spec.check.k_max

    verifier = MacroStepRefinementVerifier(ts_a, ts_b)
    result = verifier.verify(seed=seed, max_boundaries=max_boundaries)

    return {
        "seed": seed,
        "is_equivalent": result.is_equivalent,
        "boundaries_checked": result.boundaries_checked,
        "total_steps_a": result.total_steps_a,
        "total_steps_b": result.total_steps_b,
        "step_profile_summary": result.step_profile_summary,
        "failure": {
            "boundary_k": result.failure.boundary_k,
            "reason": result.failure.reason,
            "sim_time_a": result.failure.sim_time_a,
            "sim_time_b": result.failure.sim_time_b,
        } if result.failure else None,
    }


def run_msre_verification(spec_path: str, end_time: float = 10000.0, verbose: bool = True):
    """
    Run MSRE verification from a specification file.

    Supports multi-seed: runs all seeds and reports aggregate results.
    """
    spec_file = Path(spec_path)
    base_path = spec_file.parent

    print("=" * 70)
    print("  MACRO-STEP REFINEMENT EQUIVALENCE VERIFICATION")
    print("=" * 70)

    spec = load_verification_spec(spec_path)

    run_length = spec.check.run_length if spec.check.run_length else end_time
    print(f"\n  Verification: {spec.name}")
    print(f"  Seeds: {len(spec.seeds)} total")
    print(f"  Models: {[m.name for m in spec.models]}")
    print(f"  Labels defined: {len(spec.labels)}")
    print(f"  Run length: {run_length}")

    if len(spec.models) != 2:
        raise ValueError(f"Expected exactly 2 models, got {len(spec.models)}")

    seed_results = []
    failed_seeds = []

    print(f"\n  Running {len(spec.seeds)} seed(s)...")

    for i, seed in enumerate(spec.seeds):
        print(f"  [{i+1}/{len(spec.seeds)}] Seed {seed}...", end="", flush=True)
        t0 = time.time()

        result = run_single_seed_msre(spec, base_path, seed, run_length)
        elapsed = time.time() - t0

        seed_results.append(result)

        if result["is_equivalent"]:
            summary = result.get("step_profile_summary", {})
            m_mean = summary.get("m_mean", 0)
            n_mean = summary.get("n_mean", 0)
            print(f" EQUIVALENT ({result['boundaries_checked']} boundaries, "
                  f"m={m_mean:.1f} n={n_mean:.1f}, {elapsed:.1f}s)")
        else:
            print(f" NOT EQUIVALENT (k={result['failure']['boundary_k']}, "
                  f"reason={result['failure']['reason']})")
            failed_seeds.append(seed)

    model_names = [m.name for m in spec.models]
    name_a, name_b = model_names[0], model_names[1]
    all_equivalent = len(failed_seeds) == 0
    equivalent_count = len(spec.seeds) - len(failed_seeds)

    print("\n" + "=" * 70)
    if all_equivalent:
        print(f"  RESULT: MACRO-STEP REFINEMENT EQUIVALENT")
        print(f"  All {len(spec.seeds)} seeds verified equivalent!")

        avg_boundaries = sum(r["boundaries_checked"] for r in seed_results) / len(seed_results)
        avg_steps_a = sum(r["total_steps_a"] for r in seed_results) / len(seed_results)
        avg_steps_b = sum(r["total_steps_b"] for r in seed_results) / len(seed_results)
        print(f"  Average: {avg_boundaries:.0f} boundaries, "
              f"{avg_steps_a:.0f} steps ({name_a}), "
              f"{avg_steps_b:.0f} steps ({name_b})")
    else:
        print(f"  RESULT: NOT MACRO-STEP REFINEMENT EQUIVALENT")
        print(f"  {equivalent_count}/{len(spec.seeds)} seeds equivalent, "
              f"{len(failed_seeds)} failed")
        print(f"  Failed seeds: {failed_seeds}")
    print("=" * 70)

    output = {
        "verification": spec.name,
        "check_type": "macro_step_refinement",
        "seeds": spec.seeds,
        "num_seeds": len(spec.seeds),
        "run_length": run_length,
        "equivalent_count": equivalent_count,
        "failed_seeds": failed_seeds,
        "is_equivalent": all_equivalent,
        "status": "EQUIVALENT" if all_equivalent else "NOT_EQUIVALENT",
        "per_seed_results": seed_results,
    }

    if spec.output.file_path:
        output_path = base_path / spec.output.file_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\n  Results written to: {output_path}")

    return output


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_verification_msre.py <verification.simasm> [end_time]")
        sys.exit(1)

    spec_path = sys.argv[1]
    end_time = float(sys.argv[2]) if len(sys.argv) > 2 else 10000.0
    result = run_msre_verification(spec_path, end_time=end_time)
    sys.exit(0 if result["is_equivalent"] else 1)


if __name__ == "__main__":
    main()
