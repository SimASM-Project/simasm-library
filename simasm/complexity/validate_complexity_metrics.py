#!/usr/bin/env python3
"""
Empirical Validation of ASM Complexity Metrics

This script validates the complexity metrics framework by:
1. Running HET analyzer on tandem N-queue models
2. Measuring actual simulation runtime
3. Fitting linear regression model (Runtime ~ SMC + SUD)
4. Reporting prediction accuracy (R²)
5. Generating comparison plots

Based on: Nowack (2000) "Complexity Theory via Abstract State Machines"

Usage:
    python validate_complexity_metrics.py
    python validate_complexity_metrics.py --end-time 500.0 --seeds 42,123,456
    python validate_complexity_metrics.py --output simasm/output/complexity_validation/
"""

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
from scipy import stats

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from simasm.complexity.simasm_het_analyzer import analyze_simasm, analysis_to_dict
from simasm.parser.loader import load_file
from simasm.runtime.stepper import ASMStepper, StepperConfig


# =============================================================================
# Configuration
# =============================================================================

# Model paths
BASE_DIR = Path(__file__).parent.parent / "input" / "project_2" / "tandem_n_queue"
EG_DIR = BASE_DIR / "generated" / "eg"
ACD_DIR = BASE_DIR / "generated" / "acd"

# Default output directory
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "output" / "complexity_validation"

# N values for tandem queue models
N_VALUES = [1, 3, 5, 10, 20]

# Default simulation parameters
DEFAULT_END_TIME = 1000.0
DEFAULT_SEEDS = [42, 123, 456]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ComplexityFeatures:
    """Complexity features extracted from HET analysis."""
    model_name: str
    n: int
    formalism: str
    filepath: str
    total_rules: int
    total_het: int
    avg_het: float
    state_update_density: float
    total_updates: int
    total_conditionals: int
    total_let_bindings: int
    total_function_calls: int
    total_new_entities: int
    total_list_operations: int


@dataclass
class RuntimeMeasurement:
    """Runtime measurement for a single simulation run."""
    model_name: str
    n: int
    formalism: str
    seed: int
    end_time: float
    steps: int
    final_sim_time: float
    load_time_sec: float
    exec_time_sec: float
    total_time_sec: float


@dataclass
class RegressionResults:
    """Results from linear regression analysis."""
    r_squared: float
    adj_r_squared: float
    coefficients: Dict[str, float]
    std_errors: Dict[str, float]
    t_statistics: Dict[str, float]
    p_values: Dict[str, float]
    f_statistic: float
    f_pvalue: float
    n_observations: int
    residual_std_error: float


# =============================================================================
# Feature Extraction
# =============================================================================

def extract_complexity_features(simasm_file: str) -> ComplexityFeatures:
    """
    Run HET analyzer and extract complexity features.

    Args:
        simasm_file: Path to the .simasm file

    Returns:
        ComplexityFeatures dataclass with extracted metrics
    """
    filepath = Path(simasm_file)

    # Parse model name and metadata
    filename = filepath.stem  # e.g., "tandem_3_eg"
    parts = filename.split("_")
    n = int(parts[1])  # Extract N from tandem_N_formalism
    formalism = parts[2].upper()  # EG or ACD

    # Read and analyze source
    with open(simasm_file, 'r') as f:
        source = f.read()

    analysis = analyze_simasm(source, str(filepath))

    return ComplexityFeatures(
        model_name=filename,
        n=n,
        formalism=formalism,
        filepath=str(filepath),
        total_rules=analysis.total_rules,
        total_het=analysis.total_het,
        avg_het=analysis.avg_het,
        state_update_density=analysis.state_update_density,
        total_updates=analysis.total_updates,
        total_conditionals=analysis.total_conditionals,
        total_let_bindings=analysis.total_let_bindings,
        total_function_calls=analysis.total_function_calls,
        total_new_entities=analysis.total_new_entities,
        total_list_operations=analysis.total_list_operations
    )


def extract_all_features(model_paths: List[str]) -> pd.DataFrame:
    """
    Extract complexity features for all models.

    Args:
        model_paths: List of paths to .simasm files

    Returns:
        DataFrame with complexity features
    """
    features_list = []

    for path in model_paths:
        try:
            features = extract_complexity_features(path)
            features_list.append(asdict(features))
            print(f"  Extracted features: {features.model_name}")
        except Exception as e:
            print(f"  ERROR extracting features from {path}: {e}")

    return pd.DataFrame(features_list)


# =============================================================================
# Runtime Measurement
# =============================================================================

def measure_runtime(
    simasm_file: str,
    end_time: float,
    seed: int
) -> RuntimeMeasurement:
    """
    Run simulation and measure runtime.

    Args:
        simasm_file: Path to the .simasm file
        end_time: Simulation end time
        seed: Random seed

    Returns:
        RuntimeMeasurement with timing data
    """
    filepath = Path(simasm_file)
    filename = filepath.stem
    parts = filename.split("_")
    n = int(parts[1])
    formalism = parts[2].upper()

    # Measure load time
    load_start = time.perf_counter()
    loaded = load_file(str(simasm_file), seed=seed)
    load_time = time.perf_counter() - load_start

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

    # Measure execution time
    exec_start = time.perf_counter()
    steps = 0
    while stepper.can_step():
        stepper.step()
        steps += 1
    exec_time = time.perf_counter() - exec_start

    final_sim_time = loaded.state.get_var("sim_clocktime") or 0.0

    return RuntimeMeasurement(
        model_name=filename,
        n=n,
        formalism=formalism,
        seed=seed,
        end_time=end_time,
        steps=steps,
        final_sim_time=final_sim_time,
        load_time_sec=load_time,
        exec_time_sec=exec_time,
        total_time_sec=load_time + exec_time
    )


def measure_all_runtimes(
    model_paths: List[str],
    end_time: float,
    seeds: List[int]
) -> pd.DataFrame:
    """
    Measure runtime for all models across multiple seeds.

    Args:
        model_paths: List of paths to .simasm files
        end_time: Simulation end time
        seeds: List of random seeds

    Returns:
        DataFrame with runtime measurements
    """
    measurements = []

    for path in model_paths:
        filename = Path(path).stem
        for seed in seeds:
            try:
                measurement = measure_runtime(path, end_time, seed)
                measurements.append(asdict(measurement))
                print(f"  {filename} seed={seed}: {measurement.steps} steps, "
                      f"{measurement.exec_time_sec:.3f}s exec")
            except Exception as e:
                print(f"  ERROR measuring {filename} seed={seed}: {e}")

    return pd.DataFrame(measurements)


# =============================================================================
# Statistical Analysis
# =============================================================================

def compute_runtime_summary(runtime_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute summary statistics for runtime measurements.

    Args:
        runtime_df: DataFrame with individual runtime measurements

    Returns:
        DataFrame with mean/std statistics per model
    """
    summary = runtime_df.groupby(['model_name', 'n', 'formalism']).agg({
        'steps': ['mean', 'std'],
        'exec_time_sec': ['mean', 'std'],
        'load_time_sec': ['mean', 'std'],
        'total_time_sec': ['mean', 'std'],
        'final_sim_time': ['mean', 'std'],
    }).reset_index()

    # Flatten column names
    summary.columns = [
        '_'.join(col).strip('_') if isinstance(col, tuple) else col
        for col in summary.columns
    ]

    return summary


def fit_regression(
    features_df: pd.DataFrame,
    runtime_summary: pd.DataFrame,
    target_var: str = 'exec_time_sec_mean'
) -> Tuple[RegressionResults, pd.DataFrame]:
    """
    Fit linear regression model: Runtime ~ total_het + total_updates.

    Args:
        features_df: DataFrame with complexity features
        runtime_summary: DataFrame with runtime summary statistics
        target_var: Target variable for regression (default: exec_time_sec_mean)

    Returns:
        Tuple of (RegressionResults, merged DataFrame)
    """
    # Merge features with runtime summary
    merged = features_df.merge(
        runtime_summary,
        on=['model_name', 'n', 'formalism']
    )

    # Feature matrix (SMC = total_het, SUD approximated by total_updates)
    X = merged[['total_het', 'total_updates']].values
    y = merged[target_var].values

    n_obs = len(y)
    n_features = X.shape[1]

    # Add intercept
    X_with_intercept = np.column_stack([np.ones(n_obs), X])

    # OLS fit: beta = (X'X)^-1 X'y
    XtX_inv = np.linalg.inv(X_with_intercept.T @ X_with_intercept)
    beta = XtX_inv @ X_with_intercept.T @ y

    # Predictions and residuals
    y_pred = X_with_intercept @ beta
    residuals = y - y_pred

    # Sum of squares
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)

    # R-squared
    r_squared = 1 - (ss_res / ss_tot)

    # Adjusted R-squared
    adj_r_squared = 1 - (1 - r_squared) * (n_obs - 1) / (n_obs - n_features - 1)

    # Residual standard error
    residual_var = ss_res / (n_obs - n_features - 1)
    residual_std = np.sqrt(residual_var)

    # Standard errors of coefficients
    se_beta = np.sqrt(np.diag(XtX_inv) * residual_var)

    # t-statistics and p-values
    t_stats = beta / se_beta
    p_values = 2 * (1 - stats.t.cdf(np.abs(t_stats), df=n_obs - n_features - 1))

    # F-statistic
    ss_reg = ss_tot - ss_res
    ms_reg = ss_reg / n_features
    ms_res = ss_res / (n_obs - n_features - 1)
    f_stat = ms_reg / ms_res
    f_pvalue = 1 - stats.f.cdf(f_stat, n_features, n_obs - n_features - 1)

    # Create results
    feature_names = ['intercept', 'total_het', 'total_updates']

    results = RegressionResults(
        r_squared=float(r_squared),
        adj_r_squared=float(adj_r_squared),
        coefficients={name: float(coef) for name, coef in zip(feature_names, beta)},
        std_errors={name: float(se) for name, se in zip(feature_names, se_beta)},
        t_statistics={name: float(t) for name, t in zip(feature_names, t_stats)},
        p_values={name: float(p) for name, p in zip(feature_names, p_values)},
        f_statistic=float(f_stat),
        f_pvalue=float(f_pvalue),
        n_observations=n_obs,
        residual_std_error=float(residual_std)
    )

    # Add predictions to merged DataFrame
    merged['predicted_runtime'] = y_pred
    merged['residual'] = residuals

    return results, merged


# =============================================================================
# Visualization
# =============================================================================

def generate_plots(
    merged_df: pd.DataFrame,
    regression_results: RegressionResults,
    output_dir: Path
):
    """
    Generate visualization plots.

    Args:
        merged_df: DataFrame with features, runtime, and predictions
        regression_results: Results from linear regression
        output_dir: Directory to save plots
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
    except ImportError:
        print("  WARNING: matplotlib not available, skipping plots")
        return

    # Create figure with subplots
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # Color map for formalisms
    colors = {'EG': 'blue', 'ACD': 'orange'}

    # --- Plot 1: HET vs Runtime ---
    ax1 = axes[0, 0]
    for formalism in ['EG', 'ACD']:
        mask = merged_df['formalism'] == formalism
        ax1.scatter(
            merged_df.loc[mask, 'total_het'],
            merged_df.loc[mask, 'exec_time_sec_mean'],
            c=colors[formalism],
            label=formalism,
            s=80,
            alpha=0.7
        )
    ax1.set_xlabel('Total HET (Microstep Complexity)')
    ax1.set_ylabel('Execution Time (seconds)')
    ax1.set_title('HET vs Runtime')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # --- Plot 2: Predicted vs Actual Runtime ---
    ax2 = axes[0, 1]
    for formalism in ['EG', 'ACD']:
        mask = merged_df['formalism'] == formalism
        ax2.scatter(
            merged_df.loc[mask, 'predicted_runtime'],
            merged_df.loc[mask, 'exec_time_sec_mean'],
            c=colors[formalism],
            label=formalism,
            s=80,
            alpha=0.7
        )

    # Add diagonal line
    min_val = min(merged_df['predicted_runtime'].min(), merged_df['exec_time_sec_mean'].min())
    max_val = max(merged_df['predicted_runtime'].max(), merged_df['exec_time_sec_mean'].max())
    ax2.plot([min_val, max_val], [min_val, max_val], 'k--', alpha=0.5, label='Perfect fit')

    ax2.set_xlabel('Predicted Runtime (seconds)')
    ax2.set_ylabel('Actual Runtime (seconds)')
    ax2.set_title(f'Predicted vs Actual (R² = {regression_results.r_squared:.3f})')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # --- Plot 3: N vs Runtime by Formalism ---
    ax3 = axes[1, 0]
    for formalism in ['EG', 'ACD']:
        mask = merged_df['formalism'] == formalism
        data = merged_df.loc[mask].sort_values('n')
        ax3.plot(
            data['n'],
            data['exec_time_sec_mean'],
            'o-',
            c=colors[formalism],
            label=formalism,
            markersize=8
        )
    ax3.set_xlabel('Number of Stations (N)')
    ax3.set_ylabel('Execution Time (seconds)')
    ax3.set_title('Runtime Scaling with N')
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # --- Plot 4: Residuals ---
    ax4 = axes[1, 1]
    for formalism in ['EG', 'ACD']:
        mask = merged_df['formalism'] == formalism
        ax4.scatter(
            merged_df.loc[mask, 'predicted_runtime'],
            merged_df.loc[mask, 'residual'],
            c=colors[formalism],
            label=formalism,
            s=80,
            alpha=0.7
        )
    ax4.axhline(y=0, color='k', linestyle='--', alpha=0.5)
    ax4.set_xlabel('Predicted Runtime (seconds)')
    ax4.set_ylabel('Residual (seconds)')
    ax4.set_title('Residual Plot')
    ax4.legend()
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()

    # Save figure
    plot_path = output_dir / 'complexity_vs_runtime.png'
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"  Saved plot: {plot_path}")

    # --- Additional Plot: Complexity Features by N ---
    fig2, axes2 = plt.subplots(1, 2, figsize=(12, 5))

    # HET by N
    ax = axes2[0]
    for formalism in ['EG', 'ACD']:
        mask = merged_df['formalism'] == formalism
        data = merged_df.loc[mask].sort_values('n')
        ax.plot(
            data['n'],
            data['total_het'],
            'o-',
            c=colors[formalism],
            label=formalism,
            markersize=8
        )
    ax.set_xlabel('Number of Stations (N)')
    ax.set_ylabel('Total HET')
    ax.set_title('HET Scaling with N')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Updates by N
    ax = axes2[1]
    for formalism in ['EG', 'ACD']:
        mask = merged_df['formalism'] == formalism
        data = merged_df.loc[mask].sort_values('n')
        ax.plot(
            data['n'],
            data['total_updates'],
            'o-',
            c=colors[formalism],
            label=formalism,
            markersize=8
        )
    ax.set_xlabel('Number of Stations (N)')
    ax.set_ylabel('Total Updates')
    ax.set_title('Updates Scaling with N')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    features_plot_path = output_dir / 'complexity_features_by_n.png'
    plt.savefig(features_plot_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"  Saved plot: {features_plot_path}")


# =============================================================================
# Report Generation
# =============================================================================

def print_report(
    features_df: pd.DataFrame,
    runtime_summary: pd.DataFrame,
    regression_results: RegressionResults,
    merged_df: pd.DataFrame
):
    """Print analysis report to console."""

    print("\n" + "=" * 70)
    print("  ASM COMPLEXITY METRICS VALIDATION REPORT")
    print("=" * 70)

    print("\n1. COMPLEXITY FEATURES")
    print("-" * 70)
    print(f"{'Model':<20} {'N':>5} {'Form':>5} {'Rules':>6} {'HET':>8} {'Updates':>8} {'Cond':>6}")
    print("-" * 70)
    for _, row in features_df.iterrows():
        print(f"{row['model_name']:<20} {row['n']:>5} {row['formalism']:>5} "
              f"{row['total_rules']:>6} {row['total_het']:>8} "
              f"{row['total_updates']:>8} {row['total_conditionals']:>6}")

    print("\n2. RUNTIME SUMMARY")
    print("-" * 70)
    print(f"{'Model':<20} {'N':>5} {'Form':>5} {'Steps':>10} {'Exec(s)':>10} {'Std':>8}")
    print("-" * 70)
    for _, row in runtime_summary.iterrows():
        print(f"{row['model_name']:<20} {row['n']:>5} {row['formalism']:>5} "
              f"{row['steps_mean']:>10.0f} {row['exec_time_sec_mean']:>10.3f} "
              f"{row['exec_time_sec_std']:>8.3f}")

    print("\n3. REGRESSION RESULTS")
    print("-" * 70)
    print(f"  Model: Runtime ~ total_het + total_updates")
    print(f"  Observations: {regression_results.n_observations}")
    print()
    print(f"  R-squared:         {regression_results.r_squared:.4f}")
    print(f"  Adjusted R²:       {regression_results.adj_r_squared:.4f}")
    print(f"  Residual Std Err:  {regression_results.residual_std_error:.6f}")
    print(f"  F-statistic:       {regression_results.f_statistic:.4f}")
    print(f"  F p-value:         {regression_results.f_pvalue:.6f}")
    print()
    print("  Coefficients:")
    print(f"  {'Variable':<15} {'Coef':>12} {'Std Err':>12} {'t-stat':>10} {'p-value':>12}")
    print("  " + "-" * 61)
    for var in ['intercept', 'total_het', 'total_updates']:
        print(f"  {var:<15} {regression_results.coefficients[var]:>12.6f} "
              f"{regression_results.std_errors[var]:>12.6f} "
              f"{regression_results.t_statistics[var]:>10.3f} "
              f"{regression_results.p_values[var]:>12.6f}")

    print("\n4. INTERPRETATION")
    print("-" * 70)

    if regression_results.r_squared >= 0.9:
        quality = "EXCELLENT"
    elif regression_results.r_squared >= 0.7:
        quality = "GOOD"
    elif regression_results.r_squared >= 0.5:
        quality = "MODERATE"
    else:
        quality = "WEAK"

    print(f"  Predictive Power: {quality} (R² = {regression_results.r_squared:.3f})")

    # Check significance
    sig_vars = [v for v in ['total_het', 'total_updates']
                if regression_results.p_values[v] < 0.05]

    if sig_vars:
        print(f"  Significant predictors (p < 0.05): {', '.join(sig_vars)}")
    else:
        print("  No significant predictors at p < 0.05 level")

    # HET coefficient interpretation
    het_coef = regression_results.coefficients['total_het']
    if het_coef > 0:
        print(f"  Each unit increase in HET adds ~{het_coef*1000:.3f}ms to runtime")

    print("\n5. EG vs ACD COMPARISON")
    print("-" * 70)

    eg_data = merged_df[merged_df['formalism'] == 'EG']
    acd_data = merged_df[merged_df['formalism'] == 'ACD']

    print(f"  EG  - Avg HET: {eg_data['total_het'].mean():.1f}, "
          f"Avg Runtime: {eg_data['exec_time_sec_mean'].mean():.3f}s")
    print(f"  ACD - Avg HET: {acd_data['total_het'].mean():.1f}, "
          f"Avg Runtime: {acd_data['exec_time_sec_mean'].mean():.3f}s")

    if len(eg_data) > 0 and len(acd_data) > 0:
        het_ratio = acd_data['total_het'].mean() / eg_data['total_het'].mean()
        runtime_ratio = acd_data['exec_time_sec_mean'].mean() / eg_data['exec_time_sec_mean'].mean()
        print(f"  ACD/EG HET ratio: {het_ratio:.2f}x")
        print(f"  ACD/EG Runtime ratio: {runtime_ratio:.2f}x")

    print("\n" + "=" * 70)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Validate ASM complexity metrics against simulation runtime"
    )
    parser.add_argument(
        "--end-time",
        type=float,
        default=DEFAULT_END_TIME,
        help=f"Simulation end time (default: {DEFAULT_END_TIME})"
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default=",".join(map(str, DEFAULT_SEEDS)),
        help=f"Comma-separated seeds (default: {','.join(map(str, DEFAULT_SEEDS))})"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory (default: simasm/output/complexity_validation/)"
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip generating plots"
    )

    args = parser.parse_args()

    seeds = [int(s.strip()) for s in args.seeds.split(",")]
    end_time = args.end_time

    # Setup output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = DEFAULT_OUTPUT_DIR / timestamp

    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  ASM COMPLEXITY METRICS VALIDATION")
    print("=" * 70)
    print(f"\n  End time: {end_time}")
    print(f"  Seeds: {seeds}")
    print(f"  Output: {output_dir}")

    # Collect model paths
    model_paths = []
    for n in N_VALUES:
        eg_path = EG_DIR / f"tandem_{n}_eg.simasm"
        acd_path = ACD_DIR / f"tandem_{n}_acd.simasm"
        if eg_path.exists():
            model_paths.append(str(eg_path))
        if acd_path.exists():
            model_paths.append(str(acd_path))

    print(f"\n  Found {len(model_paths)} models")

    # Step 1: Extract complexity features
    print("\n" + "-" * 70)
    print("  STEP 1: Extracting Complexity Features")
    print("-" * 70)

    features_df = extract_all_features(model_paths)

    features_path = output_dir / "complexity_features.csv"
    features_df.to_csv(features_path, index=False)
    print(f"\n  Saved: {features_path}")

    # Step 2: Measure runtime
    print("\n" + "-" * 70)
    print("  STEP 2: Measuring Runtime")
    print("-" * 70)

    runtime_df = measure_all_runtimes(model_paths, end_time, seeds)

    runtime_path = output_dir / "runtime_measurements.csv"
    runtime_df.to_csv(runtime_path, index=False)
    print(f"\n  Saved: {runtime_path}")

    # Compute runtime summary
    runtime_summary = compute_runtime_summary(runtime_df)
    summary_path = output_dir / "runtime_summary.csv"
    runtime_summary.to_csv(summary_path, index=False)
    print(f"  Saved: {summary_path}")

    # Step 3: Fit regression
    print("\n" + "-" * 70)
    print("  STEP 3: Fitting Regression Model")
    print("-" * 70)

    regression_results, merged_df = fit_regression(features_df, runtime_summary)

    # Save regression results
    results_dict = {
        "r_squared": regression_results.r_squared,
        "adj_r_squared": regression_results.adj_r_squared,
        "coefficients": regression_results.coefficients,
        "std_errors": regression_results.std_errors,
        "t_statistics": regression_results.t_statistics,
        "p_values": regression_results.p_values,
        "f_statistic": regression_results.f_statistic,
        "f_pvalue": regression_results.f_pvalue,
        "n_observations": regression_results.n_observations,
        "residual_std_error": regression_results.residual_std_error
    }

    results_path = output_dir / "regression_results.json"
    with open(results_path, 'w') as f:
        json.dump(results_dict, f, indent=2)
    print(f"\n  Saved: {results_path}")

    # Save merged data
    merged_path = output_dir / "merged_data.csv"
    merged_df.to_csv(merged_path, index=False)
    print(f"  Saved: {merged_path}")

    # Step 4: Generate plots
    if not args.no_plots:
        print("\n" + "-" * 70)
        print("  STEP 4: Generating Plots")
        print("-" * 70)

        generate_plots(merged_df, regression_results, output_dir)

    # Print report
    print_report(features_df, runtime_summary, regression_results, merged_df)

    print(f"\n  All results saved to: {output_dir}")

    # Exit with appropriate code based on R²
    if regression_results.r_squared >= 0.7:
        print("\n  VALIDATION SUCCESSFUL: R² >= 0.7")
        return 0
    else:
        print(f"\n  VALIDATION: R² = {regression_results.r_squared:.3f} (target >= 0.7)")
        return 0  # Still return 0 since the script completed successfully


if __name__ == "__main__":
    sys.exit(main())
