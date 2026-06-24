#!/usr/bin/env python3
"""
Batch SMC analysis across all Event Graph models.

Discovers EG models in the standard directory layout, computes SMC for
each, and outputs results as JSON, CSV, and .smc.simasm files.

Usage:
    python -m simasm.smc_complexity.run_smc_analysis
    python -m simasm.smc_complexity.run_smc_analysis --base-dir path/to/models
    python -m simasm.smc_complexity.run_smc_analysis --output-dir path/to/output
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from datetime import datetime

from simasm.smc_complexity.api import compute_smc
from simasm.smc_complexity.smc_spec import export_smc_simasm


TOPOLOGIES = ["tandem_n_queue", "fork_join_n_queue", "feedback_n_queue"]
HELD_OUT = ["hybrid"]
SIZES = [1, 2, 3, 4, 5, 7, 10, 15, 20]


def discover_models(base_dir: Path):
    """Discover EG models in the standard directory layout."""
    models = []

    for topo_dir_name in TOPOLOGIES + HELD_OUT:
        eg_json_dir = base_dir / topo_dir_name / "eg"
        if not eg_json_dir.exists():
            for alt in ["held_out/" + topo_dir_name + "/eg"]:
                alt_path = base_dir / alt
                if alt_path.exists():
                    eg_json_dir = alt_path
                    break

        if not eg_json_dir.exists():
            continue

        for json_file in sorted(eg_json_dir.glob("*_eg.json")):
            model_name = json_file.stem
            simasm_name = model_name + ".simasm"

            simasm_dir = eg_json_dir.parent / "simasm"
            if not simasm_dir.exists():
                simasm_dir = eg_json_dir.parent / "generated" / "eg"
            if not simasm_dir.exists():
                simasm_dir = eg_json_dir

            simasm_file = simasm_dir / simasm_name
            if not simasm_file.exists():
                for candidate in simasm_dir.glob(f"*{model_name}*"):
                    if candidate.suffix == ".simasm":
                        simasm_file = candidate
                        break

            if simasm_file.exists():
                topo = topo_dir_name.replace("_n_queue", "")
                models.append({
                    "model_name": model_name,
                    "topology": topo,
                    "simasm_path": str(simasm_file),
                    "json_path": str(json_file),
                })

    return models


def main():
    parser = argparse.ArgumentParser(description="Batch SMC analysis")
    parser.add_argument("--base-dir", type=str, default=None,
                        help="Base directory containing model topologies")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory for results")
    parser.add_argument("--simasm-path", type=str, default=None,
                        help="Single .simasm file to analyze")
    parser.add_argument("--json-path", type=str, default=None,
                        help="Single JSON spec to analyze")
    args = parser.parse_args()

    if args.simasm_path and args.json_path:
        result = compute_smc(args.simasm_path, args.json_path)
        print(f"\n{'='*60}")
        print(f"SMC Analysis: {result.model_name}")
        print(f"{'='*60}")
        print(f"Events: {len(set(n.lower() for n in result.event_het))} "
              f"({', '.join(f'{n}={c}' for n, c in sorted(result.event_het.items()) if n == n.lower())})")
        print(f"C_step: {result.c_step}, C_init: {result.c_init}")
        print(f"Cycles: {result.num_cycles}")
        for c in result.cycles:
            verts = " → ".join(c.vertices)
            print(f"  c{c.index}: [{verts}] C={c.cost} T={c.period} R={c.rate:.1f}")
        print(f"SCR: {result.scr:.1f}")
        print(f"SMC: {result.smc:,.0f}")
        print(f"SMC_orig: {result.smc_original}")
        print(f"Time: {result.computation_time_ms:.2f}ms")
        return

    if args.base_dir:
        base_dir = Path(args.base_dir)
    else:
        base_dir = Path(__file__).resolve().parents[2] / "experiments" / "project_2" / "misc" / "json_models"

    output_dir = Path(args.output_dir) if args.output_dir else Path(".")

    models = discover_models(base_dir)
    if not models:
        print(f"No models found in {base_dir}")
        sys.exit(1)

    print(f"Found {len(models)} EG models in {base_dir}")
    print(f"{'='*80}")

    results = []
    errors = []
    total_start = time.perf_counter()

    for m in models:
        try:
            result = compute_smc(
                simasm_path=m["simasm_path"],
                json_path=m["json_path"],
                model_name=m["model_name"],
            )
            row = {
                "model_name": result.model_name,
                "topology": m["topology"],
                "vertex_count": result.vertex_count,
                "edge_count": result.edge_count,
                "num_cycles": result.num_cycles,
                "c_step": result.c_step,
                "c_init": result.c_init,
                "scr": round(result.scr, 2),
                "smc": round(result.smc, 2),
                "smc_original": result.smc_original,
                "t_sim": result.t_sim,
                "computation_time_ms": round(result.computation_time_ms, 2),
            }
            results.append(row)
            print(f"  {result.model_name:30s} |V|={result.vertex_count:3d} "
                  f"|E|={result.edge_count:3d} cycles={result.num_cycles:2d} "
                  f"SCR={result.scr:10.1f} SMC={result.smc:14,.0f} "
                  f"({result.computation_time_ms:.1f}ms)")

        except Exception as e:
            errors.append((m["model_name"], str(e)))
            print(f"  {m['model_name']:30s} ERROR: {e}")

    total_elapsed = (time.perf_counter() - total_start) * 1000
    print(f"{'='*80}")
    print(f"Completed: {len(results)} OK, {len(errors)} errors in {total_elapsed:.0f}ms")

    if results:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = output_dir / f"smc_results_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"JSON: {json_path}")

        csv_path = output_dir / f"smc_results_{ts}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        print(f"CSV:  {csv_path}")

    if errors:
        print(f"\nErrors:")
        for name, err in errors:
            print(f"  {name}: {err}")


if __name__ == "__main__":
    main()
