#!/usr/bin/env python3
"""
validate_held_out.py

Validate HET complexity metric on held-out topologies.

This script:
1. Loads held-out models (hybrid topology: tandem + fork-join + feedback)
2. Extracts complexity metrics (HET, SMC, CC, KC, LOC)
3. Runs simulations to measure runtime
4. Computes R² for held-out models separately from development models
5. Reports comparison between development and held-out validation

Usage:
    python validate_held_out.py --extract-only    # Extract metrics without running sims
    python validate_held_out.py --full            # Full validation with simulations
    python validate_held_out.py --report          # Generate report from existing data
"""

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple
import statistics

# Add project root to path (simasm/simasm, not simasm/simasm/simasm)
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from simasm.complexity.api import analyze_complexity
from simasm.parser.loader import load_file
from simasm.runtime.stepper import ASMStepper, StepperConfig


@dataclass
class ModelMetrics:
    """Metrics for a single model."""
    model_name: str
    topology: str
    is_held_out: bool
    het_static: int
    het_path_avg: float
    num_paths: int
    vertex_count: int
    edge_count: int
    cyclomatic_number: int
    total_rules: int
    total_updates: int
    loc: int = 0
    kc: float = 0.0
    runtime_mean: float = 0.0
    runtime_std: float = 0.0
    steps_mean: float = 0.0


def count_lines_of_code(simasm_path: Path) -> int:
    """Count non-blank, non-comment lines in SimASM file."""
    if not simasm_path.exists():
        return 0
    count = 0
    with open(simasm_path, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith('//') and not stripped.startswith('#'):
                count += 1
    return count


def compute_kolmogorov_complexity(simasm_path: Path) -> float:
    """Approximate Kolmogorov complexity via compression."""
    import zlib
    import math
    if not simasm_path.exists():
        return 0.0
    with open(simasm_path, 'rb') as f:
        data = f.read()
    compressed = zlib.compress(data, level=9)
    return math.log2(len(compressed)) if len(compressed) > 0 else 0.0


def discover_models(base_dir: Path, topology_dirs: List[str], is_held_out: bool) -> List[Dict[str, Any]]:
    """Discover all models in given topology directories."""
    models = []
    for topology in topology_dirs:
        eg_dir = base_dir / topology / "eg"
        generated_dir = base_dir / topology / "generated" / "eg"
        if not eg_dir.exists():
            continue
        for json_file in eg_dir.glob("*_eg.json"):
            model_name = json_file.stem.replace("_eg", "")
            simasm_file = generated_dir / f"{model_name}_eg.simasm"
            models.append({
                "model_name": model_name,
                "topology": topology,
                "json_path": json_file,
                "simasm_path": simasm_file,
                "is_held_out": is_held_out
            })
    return models


def extract_metrics(model_info: Dict[str, Any], verbose: bool = True) -> Optional[ModelMetrics]:
    """Extract all complexity metrics for a model."""
    json_path = model_info["json_path"]
    simasm_path = model_info["simasm_path"]
    if not simasm_path.exists():
        if verbose:
            print(f"  SKIP {model_info['model_name']}: SimASM file not found")
        return None
    if verbose:
        print(f"  Analyzing {model_info['model_name']}...")
    try:
        result = analyze_complexity(simasm_path, json_path)
        loc = count_lines_of_code(simasm_path)
        kc = compute_kolmogorov_complexity(simasm_path)
        return ModelMetrics(
            model_name=model_info["model_name"],
            topology=model_info["topology"],
            is_held_out=model_info["is_held_out"],
            het_static=result.het_static,
            het_path_avg=result.het_path_avg,
            num_paths=result.num_paths,
            vertex_count=result.vertex_count,
            edge_count=result.edge_count,
            cyclomatic_number=result.cyclomatic_number,
            total_rules=result.total_rules,
            total_updates=result.total_updates,
            loc=loc,
            kc=kc
        )
    except Exception as e:
        if verbose:
            print(f"    ERROR: {e}")
        return None


def run_simulation(simasm_path: Path, end_time: float, seed: int) -> Tuple[float, int]:
    """Run a single simulation and return (runtime, steps)."""
    loaded = load_file(str(simasm_path), seed=seed)
    main_rule = loaded.rules.get(loaded.main_rule_name)
    config = StepperConfig(time_var="sim_clocktime", end_time=end_time)
    stepper = ASMStepper(
        state=loaded.state,
        main_rule=main_rule,
        rule_evaluator=loaded.rule_evaluator,
        config=config,
    )
    exec_start = time.perf_counter()
    steps = 0
    while stepper.can_step():
        stepper.step()
        steps += 1
    exec_time = time.perf_counter() - exec_start
    return exec_time, steps


def measure_runtime(model_info: Dict[str, Any], seeds: List[int], end_time: float,
                   verbose: bool = True) -> Tuple[float, float, float]:
    """Measure runtime across multiple seeds. Returns (mean, std, steps_mean)."""
    simasm_path = model_info["simasm_path"]
    if not simasm_path.exists():
        return 0.0, 0.0, 0.0

    runtimes = []
    all_steps = []

    for seed in seeds:
        try:
            rt, steps = run_simulation(simasm_path, end_time, seed)
            runtimes.append(rt)
            all_steps.append(steps)
            if verbose:
                print(f"    seed={seed}: {steps} steps, {rt:.3f}s")
        except Exception as e:
            if verbose:
                print(f"    seed={seed}: ERROR - {e}")

    if not runtimes:
        return 0.0, 0.0, 0.0

    mean_rt = statistics.mean(runtimes)
    std_rt = statistics.stdev(runtimes) if len(runtimes) > 1 else 0.0
    mean_steps = statistics.mean(all_steps)

    return mean_rt, std_rt, mean_steps


def compute_r_squared(x: List[float], y: List[float]) -> Tuple[float, float, float]:
    """Compute R², slope, intercept between x and y."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0, 0.0, 0.0
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    ss_tot = sum((yi - mean_y) ** 2 for yi in y)
    if var_x == 0 or ss_tot == 0:
        return 0.0, 0.0, 0.0
    slope = cov_xy / var_x
    intercept = mean_y - slope * mean_x
    y_pred = [slope * xi + intercept for xi in x]
    ss_res = sum((yi - ypi) ** 2 for yi, ypi in zip(y, y_pred))
    r_sq = 1.0 - (ss_res / ss_tot)
    return r_sq, slope, intercept


def generate_report(metrics: List[ModelMetrics], output_dir: Path) -> None:
    """Generate validation report with R² comparison."""
    output_dir.mkdir(parents=True, exist_ok=True)

    dev_models = [m for m in metrics if not m.is_held_out and m.runtime_mean > 0]
    held_out_models = [m for m in metrics if m.is_held_out and m.runtime_mean > 0]

    report = []
    report.append("=" * 70)
    report.append("  HET COMPLEXITY METRIC: HELD-OUT VALIDATION REPORT")
    report.append("=" * 70)
    report.append(f"\nGenerated: {datetime.now().isoformat()}")
    report.append(f"\nDevelopment models with runtime: {len(dev_models)}")
    report.append(f"Held-out models with runtime: {len(held_out_models)}")

    # R² Analysis
    report.append("\n" + "-" * 70)
    report.append("  R² ANALYSIS: HET vs RUNTIME")
    report.append("-" * 70)

    # Development set R²
    if len(dev_models) >= 2:
        dev_het = [m.het_path_avg for m in dev_models]
        dev_rt = [m.runtime_mean for m in dev_models]
        dev_r2, dev_slope, dev_int = compute_r_squared(dev_het, dev_rt)
        report.append(f"\nDevelopment Set (n={len(dev_models)}):")
        report.append(f"  HET R² = {dev_r2:.4f}")
        report.append(f"  Slope = {dev_slope:.6f} (seconds per HET unit)")

        # SMC R² for comparison
        dev_smc = [m.het_static for m in dev_models]
        smc_r2, _, _ = compute_r_squared(dev_smc, dev_rt)
        report.append(f"  SMC R² = {smc_r2:.4f}")

        # CC R²
        dev_cc = [m.cyclomatic_number for m in dev_models]
        cc_r2, _, _ = compute_r_squared(dev_cc, dev_rt)
        report.append(f"  CC R² = {cc_r2:.4f}")

    # Held-out set R²
    if len(held_out_models) >= 2:
        ho_het = [m.het_path_avg for m in held_out_models]
        ho_rt = [m.runtime_mean for m in held_out_models]
        ho_r2, ho_slope, ho_int = compute_r_squared(ho_het, ho_rt)
        report.append(f"\nHeld-Out Set (n={len(held_out_models)}):")
        report.append(f"  HET R² = {ho_r2:.4f}")
        report.append(f"  Slope = {ho_slope:.6f}")

        ho_smc = [m.het_static for m in held_out_models]
        smc_r2, _, _ = compute_r_squared(ho_smc, ho_rt)
        report.append(f"  SMC R² = {smc_r2:.4f}")

        ho_cc = [m.cyclomatic_number for m in held_out_models]
        cc_r2, _, _ = compute_r_squared(ho_cc, ho_rt)
        report.append(f"  CC R² = {cc_r2:.4f}")

    # Combined analysis
    all_with_runtime = dev_models + held_out_models
    if len(all_with_runtime) >= 2:
        all_het = [m.het_path_avg for m in all_with_runtime]
        all_rt = [m.runtime_mean for m in all_with_runtime]
        all_r2, all_slope, _ = compute_r_squared(all_het, all_rt)
        report.append(f"\nCombined (n={len(all_with_runtime)}):")
        report.append(f"  HET R² = {all_r2:.4f}")

    # Generalization gap
    if len(dev_models) >= 2 and len(held_out_models) >= 2:
        gap = dev_r2 - ho_r2
        report.append(f"\n  Generalization Gap (Dev - HeldOut): {gap:+.4f}")
        if abs(gap) < 0.05:
            report.append("  -> Excellent generalization (gap < 0.05)")
        elif abs(gap) < 0.10:
            report.append("  -> Good generalization (gap < 0.10)")
        else:
            report.append("  -> Potential overfitting (gap >= 0.10)")

    # Model details table
    report.append("\n" + "-" * 70)
    report.append("  MODEL DETAILS")
    report.append("-" * 70)
    report.append(f"\n{'Model':<25} {'Set':<6} {'HET':>8} {'Runtime':>10} {'Steps':>12}")
    report.append("-" * 70)

    for m in sorted(all_with_runtime, key=lambda x: (x.is_held_out, x.runtime_mean)):
        set_label = "HELD" if m.is_held_out else "DEV"
        report.append(f"{m.model_name:<25} {set_label:<6} {m.het_path_avg:>8.1f} "
                     f"{m.runtime_mean:>10.3f}s {m.steps_mean:>12.0f}")

    # Print and save
    report_text = "\n".join(report)
    print(report_text)

    report_path = output_dir / "held_out_validation_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    # Save metrics as JSON
    metrics_path = output_dir / "held_out_metrics.json"
    metrics_data = [asdict(m) for m in metrics]
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2)

    print(f"\nReport saved to: {report_path}")
    print(f"Metrics saved to: {metrics_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate HET on held-out topologies")
    parser.add_argument("--extract-only", action="store_true", help="Extract metrics only")
    parser.add_argument("--full", action="store_true", help="Full validation with simulations")
    parser.add_argument("--report", action="store_true", help="Generate report from existing data")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")
    parser.add_argument("--end-time", type=float, default=1000.0, help="Simulation end time")
    parser.add_argument("--seeds", type=str, default="42,123,456", help="Comma-separated seeds")
    parser.add_argument("--reps", type=int, default=3, help="Number of replications")

    args = parser.parse_args()

    if not any([args.extract_only, args.full, args.report]):
        args.full = True  # Default to full validation

    seeds = [int(s.strip()) for s in args.seeds.split(",")][:args.reps]
    verbose = not args.quiet

    # Paths
    project_2_dir = project_root / "simasm" / "input" / "project_2"
    held_out_dir = project_2_dir / "held_out"
    output_dir = project_root / "simasm" / "output" / "held_out_validation" / datetime.now().strftime("%Y%m%d_%H%M%S")

    dev_topologies = ["tandem_n_queue", "fork_join_n_queue", "feedback_n_queue"]
    # Hybrid is now part of development set (33 models total)
    held_out_topologies = ["hybrid", "assembly_rework", "emergency_dept"]

    print("=" * 70)
    print("  HET COMPLEXITY METRIC: HELD-OUT VALIDATION")
    print("=" * 70)
    print(f"\n  End time: {args.end_time}")
    print(f"  Seeds: {seeds}")

    # Discover models
    print("\nDiscovering models...")
    dev_models = discover_models(project_2_dir, dev_topologies, is_held_out=False)
    held_out_models = discover_models(held_out_dir, held_out_topologies, is_held_out=True)
    all_model_info = dev_models + held_out_models
    print(f"  Development models: {len(dev_models)}")
    print(f"  Held-out models: {len(held_out_models)}")

    # Extract metrics
    print("\nExtracting complexity metrics...")
    all_metrics = []
    for model_info in all_model_info:
        metrics = extract_metrics(model_info, verbose=verbose)
        if metrics:
            all_metrics.append(metrics)
    print(f"\nSuccessfully analyzed: {len(all_metrics)} models")

    # Run simulations if requested
    if args.full:
        print("\n" + "-" * 70)
        print("  RUNNING SIMULATIONS")
        print("-" * 70)

        for metrics in all_metrics:
            # Find corresponding model_info
            model_info = next((m for m in all_model_info if m["model_name"] == metrics.model_name), None)
            if model_info is None:
                continue

            print(f"\n  {metrics.model_name}:")
            mean_rt, std_rt, mean_steps = measure_runtime(
                model_info, seeds, args.end_time, verbose=verbose
            )
            metrics.runtime_mean = mean_rt
            metrics.runtime_std = std_rt
            metrics.steps_mean = mean_steps

            if mean_rt > 0:
                print(f"    -> Mean: {mean_rt:.3f}s ± {std_rt:.3f}s")

    # Generate report
    generate_report(all_metrics, output_dir)


if __name__ == "__main__":
    main()
