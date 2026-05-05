"""Command 1: 51-model LOOCV validation (Section 5 of paper).

Discovers all benchmark models, computes SMC/CC/LOC/KC, measures runtimes
via o2despy_eg, then runs LOOCV on three pools (27 homogeneous, 24
heterogeneous, 51 combined).
"""

import sys
import time
from pathlib import Path

import numpy as np

from simasm.reproduce.runtime_measure import measure_runtime
from simasm.reproduce.metrics import compute_cc, compute_loc, compute_kc
from simasm.reproduce.statistics import fit_loglog, run_loocv, sign_test
from simasm.smc_complexity import compute_smc

MODELS_DIR = Path(__file__).parent.parent / "models"
SIMASM_DIR = Path(__file__).parent.parent / "models_simasm"

HOMOGENEOUS_TOPOLOGIES = ["tandem", "fork_join", "feedback"]
SIZES = [1, 2, 3, 4, 5, 7, 10, 15, 20]

HET_TOPOLOGIES = ["tandem", "fork_join", "feedback"]
HET_SIZES = [5, 10]
HET_PATTERNS = ["hetgrad", "hetbottle"]
HET_IATS = [10, 30]


def _discover_models():
    """Discover all 51 benchmark models from the models directory.

    Returns list of dicts with keys: name, json_path, simasm_path, pool.
    """
    models = []

    for topo in HOMOGENEOUS_TOPOLOGIES:
        for n in SIZES:
            name = f"{topo}_{n}_eg"
            json_p = MODELS_DIR / f"{name}.json"
            simasm_p = SIMASM_DIR / f"{name}.simasm"
            if json_p.exists() and simasm_p.exists():
                models.append({
                    "name": name, "json_path": json_p,
                    "simasm_path": simasm_p, "pool": "homogeneous",
                })

    for topo in HET_TOPOLOGIES:
        for n in HET_SIZES:
            for pat in HET_PATTERNS:
                for iat in HET_IATS:
                    name = f"{topo}_{n}_{pat}_iat{iat}_eg"
                    json_p = MODELS_DIR / f"{name}.json"
                    simasm_p = SIMASM_DIR / f"{name}.simasm"
                    if json_p.exists() and simasm_p.exists():
                        models.append({
                            "name": name, "json_path": json_p,
                            "simasm_path": simasm_p, "pool": "heterogeneous",
                        })

    return models


def _print_table(title, headers, rows, col_widths=None):
    """Print a formatted table to stdout."""
    if col_widths is None:
        col_widths = [max(len(h), max((len(str(r[i])) for r in rows), default=0)) + 2
                      for i, h in enumerate(headers)]

    print(f"\n{'=' * sum(col_widths)}")
    print(f"  {title}")
    print(f"{'=' * sum(col_widths)}")
    header_line = "".join(h.ljust(w) for h, w in zip(headers, col_widths))
    print(header_line)
    print("-" * sum(col_widths))
    for row in rows:
        print("".join(str(v).ljust(w) for v, w in zip(row, col_widths)))
    print()


def run(verbose=False):
    """Run the full 51-model LOOCV experiment."""
    models = _discover_models()
    homo = [m for m in models if m["pool"] == "homogeneous"]
    het = [m for m in models if m["pool"] == "heterogeneous"]

    print(f"Discovered {len(models)} models ({len(homo)} homogeneous, {len(het)} heterogeneous)")
    if len(models) < 51:
        print(f"WARNING: Expected 51 models, found {len(models)}. Some models may be missing.")
    print()

    # Phase 1: Compute complexity metrics
    print("Phase 1: Computing complexity metrics...")
    total_start = time.perf_counter()

    for i, m in enumerate(models, 1):
        t0 = time.perf_counter()
        smc_result = compute_smc(str(m["simasm_path"]), str(m["json_path"]))
        smc_ms = (time.perf_counter() - t0) * 1000
        m["smc"] = smc_result.smc
        m["cc"] = compute_cc(m["json_path"])
        m["loc"] = compute_loc(m["simasm_path"])
        m["kc"] = compute_kc(m["simasm_path"])
        m["smc_ms"] = smc_ms
        if verbose:
            print(f"  [{i}/{len(models)}] {m['name']}: SMC={m['smc']:.1f} CC={m['cc']} "
                  f"LOC={m['loc']} KC={m['kc']:.1f} ({smc_ms:.1f}ms)")

    metric_time = time.perf_counter() - total_start
    print(f"  Metrics computed in {metric_time:.1f}s "
          f"(mean SMC time: {np.mean([m['smc_ms'] for m in models]):.1f}ms)")

    # Phase 2: Measure runtimes
    print(f"\nPhase 2: Measuring runtimes (30 reps x {len(models)} models)...")
    runtime_start = time.perf_counter()

    for i, m in enumerate(models, 1):
        print(f"  [{i}/{len(models)}] {m['name']}...", end="", flush=True)
        rt = measure_runtime(m["json_path"])
        m["runtime"] = rt["runtime_mean"]
        m["runtime_std"] = rt["runtime_std"]
        print(f" {m['runtime']:.4f}s (+/- {m['runtime_std']:.4f}s)")

    runtime_time = time.perf_counter() - runtime_start
    print(f"  Runtimes measured in {runtime_time:.1f}s")

    # Phase 3: LOOCV analysis
    print("\nPhase 3: Running LOOCV analysis...")

    metric_names = ["SMC", "CC", "LOC", "KC"]
    metric_keys = ["smc", "cc", "loc", "kc"]

    pools = [
        ("Homogeneous (27)", homo),
        ("Heterogeneous (24)", het),
        ("Combined (51)", models),
    ]

    for pool_name, pool_models in pools:
        if len(pool_models) < 3:
            print(f"\n  Skipping {pool_name}: too few models ({len(pool_models)})")
            continue

        runtimes = [m["runtime"] for m in pool_models]

        # Training R²
        r2_row = [pool_name]
        for key in metric_keys:
            vals = [m[key] for m in pool_models]
            reg = fit_loglog(vals, runtimes)
            r2_row.append(f"{reg.r_squared:.3f}")

        # LOOCV
        loocv_results = {}
        for key, name in zip(metric_keys, metric_names):
            vals = [m[key] for m in pool_models]
            loocv_results[key] = run_loocv(vals, runtimes)

        # Print results
        rows = []
        smc_loocv = loocv_results["smc"]
        for key, name in zip(metric_keys, metric_names):
            lcv = loocv_results[key]
            if key == "smc":
                sign_str = "—"
                p_str = "—"
            else:
                wins, total, p_val = sign_test(
                    smc_loocv.loocv_errors, lcv.loocv_errors)
                sign_str = f"{wins}/{total}"
                p_str = f"{p_val:.4f}" if p_val >= 0.0001 else "<0.0001"

            rows.append([
                name,
                f"{lcv.q_squared:.3f}",
                f"{lcv.mape:.1f}",
                sign_str,
                p_str,
            ])

        _print_table(
            f"LOOCV Results — {pool_name}",
            ["Metric", "Q²", "MAPE(%)", "Sign(wins/n)", "p-value"],
            rows,
        )

    # Training R² summary
    print("\n--- Training R² Summary ---")
    rows = []
    for pool_name, pool_models in pools:
        if len(pool_models) < 3:
            continue
        runtimes = [m["runtime"] for m in pool_models]
        row = [pool_name]
        for key in metric_keys:
            vals = [m[key] for m in pool_models]
            reg = fit_loglog(vals, runtimes)
            row.append(f"{reg.r_squared:.3f}")
        rows.append(row)

    _print_table(
        "Training R² by Pool",
        ["Pool", "SMC", "CC", "LOC", "KC"],
        rows,
    )

    # SMC computation time summary
    smc_times = [m["smc_ms"] for m in models]
    print(f"SMC computation time: mean={np.mean(smc_times):.1f}ms, "
          f"median={np.median(smc_times):.1f}ms, max={np.max(smc_times):.1f}ms")

    total_time = time.perf_counter() - total_start
    print(f"\nTotal experiment time: {total_time:.1f}s ({total_time/60:.1f} min)")

    return models
