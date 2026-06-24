#!/usr/bin/env python3
"""
Batch SMC profiler analysis across all Event Graph models.

Runs compute_smc_profiled() on all EG .simasm files (no JSON needed),
optionally cross-validates against the JSON pipeline, and outputs
results as JSON and CSV.

Usage:
    python -m simasm.smc_complexity.profiler.run_profiler
    python -m simasm.smc_complexity.profiler.run_profiler --cross-validate
    python -m simasm.smc_complexity.profiler.run_profiler --output-dir path/to/output
    python -m simasm.smc_complexity.profiler.run_profiler --simasm-path model.simasm
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from datetime import datetime

from simasm.smc_complexity.profiler import compute_smc_profiled


TOPOLOGIES = ["tandem_n_queue", "fork_join_n_queue", "feedback_n_queue"]
SIZES = [1, 2, 3, 4, 5, 7, 10, 15, 20]


def discover_eg_models(base_dir: Path):
    models = []
    for topo_dir_name in TOPOLOGIES:
        eg_dir = base_dir / topo_dir_name / "generated" / "eg"
        if not eg_dir.exists():
            continue

        json_dir = base_dir / topo_dir_name / "eg"
        topo = topo_dir_name.replace("_n_queue", "")

        for simasm_file in sorted(eg_dir.glob("*_eg.simasm")):
            model_name = simasm_file.stem
            json_file = json_dir / f"{model_name}.json" if json_dir.exists() else None
            if json_file and not json_file.exists():
                json_file = None

            models.append({
                "model_name": model_name,
                "topology": topo,
                "simasm_path": str(simasm_file),
                "json_path": str(json_file) if json_file else None,
            })

    return models


def run_single(simasm_path: str, model_name: str = None):
    result = compute_smc_profiled(simasm_path, model_name=model_name)
    print(f"\n{'='*60}")
    print(f"SMC Profiler: {result.model_name}")
    print(f"{'='*60}")
    print(f"Vertices: {result.vertex_count}  Edges: {result.edge_count}")
    print(f"Streams: {len(result.streams)} "
          f"({', '.join(f'{s.var_name}~{s.distribution}' for s in result.streams.values())})")
    print(f"Cycles: {result.num_cycles}")
    for c in result.cycles:
        verts = " -> ".join(c.vertices)
        print(f"  c{c.index}: [{verts}] C={c.cost} T={c.period:.2f} R={c.rate:.1f}")
    print(f"SCR: {result.scr:.1f}")
    print(f"SMC: {result.smc:,.0f}")
    print(f"SMC_orig: {result.smc_original}")
    print(f"Time: {result.computation_time_ms:.2f}ms")
    return result


def run_batch(base_dir: Path, output_dir: Path, cross_validate: bool = False):
    models = discover_eg_models(base_dir)
    if not models:
        print(f"No EG models found in {base_dir}")
        sys.exit(1)

    print(f"Found {len(models)} EG models in {base_dir}")
    print(f"{'='*90}")

    if cross_validate:
        print(f"{'Model':30s} | {'SCR_prof':>10s} | {'SCR_json':>10s} | {'Match':>5s} | {'Time':>8s}")
        print(f"{'-'*30}-+-{'-'*10}-+-{'-'*10}-+-{'-'*5}-+-{'-'*8}")
    else:
        print(f"{'Model':30s} | {'|V|':>4s} {'|E|':>4s} {'Cyc':>3s} | "
              f"{'SCR':>10s} {'SMC':>14s} | {'Time':>8s}")
        print(f"{'-'*30}-+-{'-'*13}-+-{'-'*26}-+-{'-'*8}")

    results = []
    errors = []
    xv_pass = 0
    xv_fail = 0
    total_start = time.perf_counter()

    for m in models:
        try:
            result = compute_smc_profiled(
                m["simasm_path"],
                model_name=m["model_name"],
            )

            row = {
                "model_name": result.model_name,
                "topology": m["topology"],
                "vertex_count": result.vertex_count,
                "edge_count": result.edge_count,
                "num_cycles": result.num_cycles,
                "scr": round(result.scr, 2),
                "smc": round(result.smc, 2),
                "smc_original": result.smc_original,
                "t_sim": result.t_sim,
                "computation_time_ms": round(result.computation_time_ms, 2),
            }

            if cross_validate and m["json_path"]:
                from simasm.smc_complexity.api import compute_smc
                json_result = compute_smc(m["simasm_path"], m["json_path"])
                match = abs(result.scr - json_result.scr) < 0.01
                row["scr_json"] = round(json_result.scr, 2)
                row["match"] = match
                symbol = "Y" if match else "N"
                if match:
                    xv_pass += 1
                else:
                    xv_fail += 1
                print(f"  {result.model_name:30s} | {result.scr:10.1f} | "
                      f"{json_result.scr:10.1f} | {symbol:>5s} | "
                      f"{result.computation_time_ms:7.1f}ms")
            else:
                print(f"  {result.model_name:30s} | {result.vertex_count:3d} "
                      f"{result.edge_count:3d} {result.num_cycles:3d} | "
                      f"{result.scr:10.1f} {result.smc:14,.0f} | "
                      f"{result.computation_time_ms:7.1f}ms")

            results.append(row)

        except Exception as e:
            errors.append((m["model_name"], str(e)))
            print(f"  {m['model_name']:30s} ERROR: {e}")

    total_elapsed = (time.perf_counter() - total_start) * 1000
    print(f"{'='*90}")
    print(f"Completed: {len(results)} OK, {len(errors)} errors in {total_elapsed:.0f}ms")

    if cross_validate:
        print(f"Cross-validation: {xv_pass} pass, {xv_fail} fail "
              f"out of {xv_pass + xv_fail} compared")

    if results:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        json_path = output_dir / f"profiler_results_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"JSON: {json_path}")

        csv_path = output_dir / f"profiler_results_{ts}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        print(f"CSV:  {csv_path}")

    if errors:
        print(f"\nErrors:")
        for name, err in errors:
            print(f"  {name}: {err}")

    return results, errors


def main():
    parser = argparse.ArgumentParser(description="Batch SMC profiler analysis")
    parser.add_argument("--base-dir", type=str, default=None,
                        help="Base directory containing model topologies")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory for results")
    parser.add_argument("--simasm-path", type=str, default=None,
                        help="Single .simasm file to analyze")
    parser.add_argument("--cross-validate", action="store_true",
                        help="Compare profiler SCR against JSON pipeline")
    args = parser.parse_args()

    if args.simasm_path:
        run_single(args.simasm_path)
        return

    if args.base_dir:
        base_dir = Path(args.base_dir)
    else:
        base_dir = Path(__file__).resolve().parents[3] / "experiments" / "project_2" / "misc" / "json_models"

    output_dir = Path(args.output_dir) if args.output_dir else Path(".")

    run_batch(base_dir, output_dir, cross_validate=args.cross_validate)


if __name__ == "__main__":
    main()
