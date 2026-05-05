"""CLI entry point for paper reproducibility experiments.

Usage:
    simasm-reproduce loocv          Run 51-model LOOCV validation (Section 5)
    simasm-reproduce warehouse      Run warehouse case study (Section 6)
    simasm-reproduce all            Run both experiments sequentially

Options:
    -v, --verbose   Print per-model details during execution
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="simasm-reproduce",
        description="Reproduce experiments from the SMC paper.",
    )
    parser.add_argument(
        "experiment",
        choices=["loocv", "warehouse", "all"],
        help="Which experiment to run: "
             "'loocv' = 51-model LOOCV (Section 5), "
             "'warehouse' = warehouse case study (Section 6), "
             "'all' = both sequentially.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print per-model details.",
    )

    args = parser.parse_args()

    print()
    print("=" * 65)
    print("  SimASM — Reproducing SMC Paper Experiments")
    print("  Yeo & Li, SIMULTECH 2025")
    print("=" * 65)
    print()

    if args.experiment in ("loocv", "all"):
        from simasm.reproduce.loocv import run as run_loocv
        training_data = run_loocv(verbose=args.verbose)

    if args.experiment == "warehouse":
        from simasm.reproduce.warehouse import run as run_warehouse
        run_warehouse(verbose=args.verbose)
    elif args.experiment == "all":
        print("\n" + "=" * 65)
        print("  Now running warehouse case study...")
        print("=" * 65 + "\n")
        from simasm.reproduce.warehouse import run as run_warehouse
        run_warehouse(training_data=training_data, verbose=args.verbose)


if __name__ == "__main__":
    main()
