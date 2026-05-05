"""Command 2: Warehouse out-of-sample prediction (Section 6 of paper).

Trains log-log regression on the 51-model benchmark pool, then predicts
runtime for the warehouse model. Reports APE and 95% prediction intervals.
"""

import time
from pathlib import Path

from simasm.reproduce.runtime_measure import measure_runtime
from simasm.reproduce.metrics import compute_cc, compute_loc, compute_kc
from simasm.reproduce.statistics import fit_loglog, prediction_interval
from simasm.smc_complexity import compute_smc

MODELS_DIR = Path(__file__).parent.parent / "models"
SIMASM_DIR = Path(__file__).parent.parent / "models_simasm"


def run(training_data=None, verbose=False):
    """Run the warehouse out-of-sample prediction experiment.

    Args:
        training_data: Optional list of model dicts from loocv.run().
            If None, runs the LOOCV experiment first to get training data.
        verbose: Print per-model details.
    """
    # Get training data
    if training_data is None:
        print("No training data provided — running 51-model benchmark first...")
        print("(Run 'simasm-reproduce loocv' separately to see full LOOCV results)")
        print()
        from simasm.reproduce.loocv import run as run_loocv
        training_data = run_loocv(verbose=verbose)

    if not training_data:
        print("ERROR: No training data available.")
        return

    # Warehouse model
    wh_json = MODELS_DIR / "warehouse_eg.json"
    wh_simasm = SIMASM_DIR / "warehouse_eg.simasm"

    if not wh_json.exists():
        print(f"ERROR: Warehouse JSON not found at {wh_json}")
        return
    if not wh_simasm.exists():
        print(f"ERROR: Warehouse SimASM not found at {wh_simasm}")
        return

    print("=" * 65)
    print("  Warehouse Out-of-Sample Prediction (Section 6)")
    print("=" * 65)

    # Compute warehouse metrics
    print("\nComputing warehouse complexity metrics...")
    t0 = time.perf_counter()
    wh_smc_result = compute_smc(str(wh_simasm), str(wh_json))
    smc_ms = (time.perf_counter() - t0) * 1000
    wh_smc = wh_smc_result.smc
    wh_cc = compute_cc(wh_json)
    wh_loc = compute_loc(wh_simasm)
    wh_kc = compute_kc(wh_simasm)

    print(f"  SMC = {wh_smc:.1f} (computed in {smc_ms:.1f}ms)")
    print(f"  CC  = {wh_cc}")
    print(f"  LOC = {wh_loc}")
    print(f"  KC  = {wh_kc:.1f}")

    # Measure warehouse runtime
    print("\nMeasuring warehouse runtime (30 reps)...")
    wh_rt = measure_runtime(wh_json)
    wh_actual = wh_rt["runtime_mean"]
    print(f"  Actual runtime: {wh_actual:.4f}s (+/- {wh_rt['runtime_std']:.4f}s)")

    # Train regressions on 51-model pool
    print("\nTraining regressions on 51-model pool...")
    runtimes = [m["runtime"] for m in training_data]

    metric_configs = [
        ("SMC", "smc", wh_smc),
        ("CC", "cc", wh_cc),
        ("LOC", "loc", wh_loc),
        ("KC", "kc", wh_kc),
    ]

    print(f"\n{'Metric':<8} {'Value':<10} {'R²':<8} {'Pred(s)':<12} "
          f"{'Actual(s)':<12} {'APE(%)':<10} {'In 95% PI?':<12}")
    print("-" * 80)

    for name, key, wh_val in metric_configs:
        vals = [m[key] for m in training_data]
        reg = fit_loglog(vals, runtimes)
        pred, lower, upper, h0 = prediction_interval(reg, wh_val)
        ape = abs(pred - wh_actual) / wh_actual * 100
        in_pi = "Yes" if lower <= wh_actual <= upper else "No"

        print(f"{name:<8} {wh_val:<10.1f} {reg.r_squared:<8.3f} {pred:<12.4f} "
              f"{wh_actual:<12.4f} {ape:<10.1f} {in_pi:<12}")

    # Prediction interval details
    print(f"\n{'Metric':<8} {'Pred(s)':<12} {'95% PI Lower':<14} {'95% PI Upper':<14} "
          f"{'Actual(s)':<12} {'In PI?':<8} {'PI Width Ratio':<16} {'Leverage h0':<12}")
    print("-" * 100)

    for name, key, wh_val in metric_configs:
        vals = [m[key] for m in training_data]
        reg = fit_loglog(vals, runtimes)
        pred, lower, upper, h0 = prediction_interval(reg, wh_val)
        in_pi = "Yes" if lower <= wh_actual <= upper else "No"
        width_ratio = upper / lower if lower > 0 else float("inf")

        print(f"{name:<8} {pred:<12.4f} {lower:<14.4f} {upper:<14.4f} "
              f"{wh_actual:<12.4f} {in_pi:<8} {width_ratio:<16.1f} {h0:<12.3f}")

    if verbose:
        print("\n--- Warehouse SMC Vertex Details ---")
        for vd in wh_smc_result.vertex_details:
            print(f"  {vd.name}: HET={vd.het_cost}, rate={vd.rate:.4f}, "
                  f"degree={vd.degree}, contribution={vd.contribution:.2f}")

    total_time = time.perf_counter() - t0
    print(f"\nWarehouse analysis complete.")
