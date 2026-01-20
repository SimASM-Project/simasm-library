"""
verification/plotting.py

Automatic visualization generation for SimASM stutter equivalence verification.

Provides:
- VerificationPlotConfig: Configuration for plot appearance
- generate_verification_plots: Main entry point for plot generation
- Individual plotting functions for different chart types

Usage:
    from simasm.verification.plotting import generate_verification_plots

    generate_verification_plots(
        result=verification_result,
        output_dir=Path("output/2026-01-09_14-23-45_Verification"),
        in_notebook=False
    )
"""

from typing import Optional, Tuple, List, Dict, Any, TYPE_CHECKING
from pathlib import Path
from dataclasses import dataclass
import sys
import os

# Set matplotlib backend BEFORE importing pyplot
import matplotlib
_in_notebook = 'ipykernel' in sys.modules
if not _in_notebook:
    if os.environ.get('DISPLAY', '') or sys.platform == 'win32':
        try:
            matplotlib.use('TkAgg')
        except:
            try:
                matplotlib.use('Qt5Agg')
            except:
                matplotlib.use('Agg')
    else:
        matplotlib.use('Agg')

import matplotlib.pyplot as plt
if not _in_notebook:
    plt.ion()
import numpy as np
from scipy import stats as scipy_stats

from simasm.log.logger import get_logger

if TYPE_CHECKING:
    from simasm.experimenter.engine import TraceVerificationResult

logger = get_logger(__name__)


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class VerificationPlotConfig:
    """Configuration for verification plot generation."""
    dpi: int = 150
    figsize_trace_comparison: Tuple[int, int] = (10, 6)
    figsize_ns_convergence: Tuple[int, int] = (12, 5)
    figsize_stutter_distribution: Tuple[int, int] = (8, 6)
    figsize_summary_table: Tuple[int, int] = (10, 4)
    show_grid: bool = True
    color_eg: str = '#2E86AB'
    color_acd: str = '#A23B72'
    color_raw: str = '#2E86AB'
    color_ns: str = '#28A745'
    color_stutter: str = '#FFC107'
    alpha_bar: float = 0.7
    alpha_line: float = 0.8


# ============================================================================
# Environment Detection
# ============================================================================

def _is_notebook() -> bool:
    """Detect if running in Jupyter notebook."""
    try:
        return 'ipykernel' in sys.modules
    except:
        return False


def _setup_matplotlib_backend(in_notebook: bool) -> None:
    """Configure matplotlib for the current environment."""
    if in_notebook:
        try:
            from IPython import get_ipython
            ipython = get_ipython()
            if ipython is not None:
                ipython.run_line_magic('matplotlib', 'inline')
        except:
            pass


# ============================================================================
# Main Entry Point
# ============================================================================

def generate_verification_plots(
    result: "TraceVerificationResult",
    output_dir: Path,
    plot_config: Optional[VerificationPlotConfig] = None,
    in_notebook: Optional[bool] = None
) -> List[plt.Figure]:
    """
    Generate all plots for a verification result.

    Creates PNG files:
    - trace_comparison.png: Grouped bar chart of raw vs no-stutter trace lengths
    - ns_convergence.png: Line plot showing no-stutter trace lengths across seeds
    - stutter_distribution.png: Box plot of stutter ratio distribution

    Args:
        result: Verification result object
        output_dir: Directory to save plots (must exist)
        plot_config: Plotting configuration (uses defaults if None)
        in_notebook: True if in Jupyter, False if CLI/API, None=auto-detect

    Returns:
        List of generated matplotlib figures
    """
    if plot_config is None:
        plot_config = VerificationPlotConfig()

    if in_notebook is None:
        in_notebook = _is_notebook()

    _setup_matplotlib_backend(in_notebook)

    logger.info(f"Generating verification plots")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Environment: {'Jupyter notebook' if in_notebook else 'CLI/API'}")

    output_dir.mkdir(parents=True, exist_ok=True)

    figures = []

    # Check if we have per-seed stats for multi-seed plots
    has_per_seed = hasattr(result, 'per_seed_stats') and result.per_seed_stats

    # 1. Trace comparison bar chart
    try:
        fig_comparison = plot_trace_comparison(result, plot_config)
        fig_comparison.savefig(
            output_dir / "trace_comparison.png",
            dpi=plot_config.dpi,
            bbox_inches='tight'
        )
        figures.append(fig_comparison)
        logger.info("Generated trace_comparison.png")
    except Exception as e:
        logger.error(f"Failed to generate trace comparison plot: {e}")

    # 2. No-stutter convergence plot (multi-seed only)
    if has_per_seed and len(result.per_seed_stats) > 1:
        try:
            fig_convergence = plot_ns_convergence(result, plot_config)
            fig_convergence.savefig(
                output_dir / "ns_convergence.png",
                dpi=plot_config.dpi,
                bbox_inches='tight'
            )
            figures.append(fig_convergence)
            logger.info("Generated ns_convergence.png")
        except Exception as e:
            logger.error(f"Failed to generate NS convergence plot: {e}")

    # 3. Stutter distribution box plot (multi-seed only)
    if has_per_seed and len(result.per_seed_stats) > 1:
        try:
            fig_stutter = plot_stutter_distribution(result, plot_config)
            fig_stutter.savefig(
                output_dir / "stutter_distribution.png",
                dpi=plot_config.dpi,
                bbox_inches='tight'
            )
            figures.append(fig_stutter)
            logger.info("Generated stutter_distribution.png")
        except Exception as e:
            logger.error(f"Failed to generate stutter distribution plot: {e}")

    # Display figures
    if in_notebook:
        for fig in figures:
            plt.figure(fig.number)
            plt.show()
    else:
        if figures:
            print(f"\n{'='*70}")
            print(f"VERIFICATION PLOTS GENERATED - {len(figures)} file(s)")
            print(f"{'='*70}")
            print(f"Files saved to: {output_dir}")
            print(f"{'='*70}\n")

            for fig in figures:
                fig.show()

            try:
                plt.pause(0.5)
            except:
                pass

            try:
                plt.show(block=True)
            except KeyboardInterrupt:
                print("\nSkipping plot display...")

    # Clean up
    for fig in figures:
        plt.close(fig)

    logger.info("Verification plot generation complete")
    return figures


# ============================================================================
# Plot Functions
# ============================================================================

def plot_trace_comparison(
    result: "TraceVerificationResult",
    config: VerificationPlotConfig
) -> plt.Figure:
    """
    Create grouped bar chart comparing trace lengths between models.

    Shows raw trace length, no-stutter trace length, and stutter steps for each model.

    Args:
        result: Verification result
        config: Plot configuration

    Returns:
        Matplotlib figure
    """
    fig, ax = plt.subplots(figsize=config.figsize_trace_comparison)

    model_names = list(result.model_stats.keys())
    if not model_names:
        ax.text(0.5, 0.5, 'No model statistics to display',
                ha='center', va='center', transform=ax.transAxes)
        return fig

    x = np.arange(len(model_names))
    width = 0.25

    # Extract statistics
    raw_lengths = []
    ns_lengths = []
    stutter_steps = []

    for name in model_names:
        stats = result.model_stats[name]
        raw = stats.get('avg_raw_length', stats.get('raw_length', 0))
        ns = stats.get('avg_ns_length', stats.get('ns_length', 0))
        raw_lengths.append(raw)
        ns_lengths.append(ns)
        stutter_steps.append(raw - ns)

    # Plot bars
    bars1 = ax.bar(x - width, raw_lengths, width, label='Raw Trace',
                   color=config.color_raw, alpha=config.alpha_bar)
    bars2 = ax.bar(x, ns_lengths, width, label='No-Stutter Trace',
                   color=config.color_ns, alpha=config.alpha_bar)
    bars3 = ax.bar(x + width, stutter_steps, width, label='Stutter Steps',
                   color=config.color_stutter, alpha=config.alpha_bar)

    # Add value labels on bars
    def add_labels(bars):
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.1f}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=9)

    add_labels(bars1)
    add_labels(bars2)
    add_labels(bars3)

    ax.set_xlabel('Model')
    ax.set_ylabel('Trace Length')
    ax.set_title('Trace Length Comparison\n(Raw vs No-Stutter vs Stutter Steps)',
                 fontsize=12, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(model_names)
    ax.legend(loc='upper right')
    ax.grid(config.show_grid, axis='y', alpha=0.3)

    plt.tight_layout()
    return fig


def plot_ns_convergence(
    result: "TraceVerificationResult",
    config: VerificationPlotConfig
) -> plt.Figure:
    """
    Create line plot showing no-stutter trace lengths across seeds.

    Both models should have identical no-stutter lengths for each seed.
    This provides visual confirmation that equivalence holds.

    Args:
        result: Verification result with per_seed_stats
        config: Plot configuration

    Returns:
        Matplotlib figure
    """
    fig, ax = plt.subplots(figsize=config.figsize_ns_convergence)

    if not result.per_seed_stats:
        ax.text(0.5, 0.5, 'No per-seed statistics available',
                ha='center', va='center', transform=ax.transAxes)
        return fig

    model_names = list(result.per_seed_stats[0].model_stats.keys())
    colors = [config.color_eg, config.color_acd]
    markers = ['o', 's']

    seeds = [s.seed for s in result.per_seed_stats]

    for i, model_name in enumerate(model_names):
        ns_lengths = []
        for seed_stats in result.per_seed_stats:
            stats = seed_stats.model_stats.get(model_name, {})
            ns_lengths.append(stats.get('ns_length', 0))

        ax.plot(seeds, ns_lengths,
                marker=markers[i % len(markers)],
                color=colors[i % len(colors)],
                label=model_name,
                linewidth=2,
                markersize=4,
                alpha=config.alpha_line)

    ax.set_xlabel('Seed')
    ax.set_ylabel('No-Stutter Trace Length')
    ax.set_title('No-Stutter Trace Length Across Seeds\n(Lines should overlap if equivalent)',
                 fontsize=12, fontweight='bold')
    ax.legend(loc='best')
    ax.grid(config.show_grid, alpha=0.3)

    # Add annotation if all equivalent
    if result.is_equivalent:
        ax.annotate('All seeds verified EQUIVALENT',
                    xy=(0.5, 0.02), xycoords='axes fraction',
                    ha='center', fontsize=10, color='green',
                    fontweight='bold')

    plt.tight_layout()
    return fig


def plot_stutter_distribution(
    result: "TraceVerificationResult",
    config: VerificationPlotConfig
) -> plt.Figure:
    """
    Create box plot showing stutter ratio distribution for each model.

    Stutter ratio = stutter_steps / raw_trace_length

    Args:
        result: Verification result with per_seed_stats
        config: Plot configuration

    Returns:
        Matplotlib figure
    """
    fig, ax = plt.subplots(figsize=config.figsize_stutter_distribution)

    if not result.per_seed_stats:
        ax.text(0.5, 0.5, 'No per-seed statistics available',
                ha='center', va='center', transform=ax.transAxes)
        return fig

    model_names = list(result.per_seed_stats[0].model_stats.keys())
    colors = [config.color_eg, config.color_acd]

    stutter_ratios = {name: [] for name in model_names}

    for seed_stats in result.per_seed_stats:
        for name in model_names:
            stats = seed_stats.model_stats.get(name, {})
            raw = stats.get('raw_length', 1)
            stutter = stats.get('stutter_steps', 0)
            ratio = stutter / raw if raw > 0 else 0
            stutter_ratios[name].append(ratio)

    # Create box plot
    data = [stutter_ratios[name] for name in model_names]
    bp = ax.boxplot(data, labels=model_names, patch_artist=True)

    # Style boxes
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    ax.set_ylabel('Stutter Ratio (stutter_steps / raw_trace)')
    ax.set_title('Stutter Ratio Distribution\n(Internal bookkeeping fraction)',
                 fontsize=12, fontweight='bold')
    ax.grid(config.show_grid, axis='y', alpha=0.3)

    # Add mean annotations
    for i, name in enumerate(model_names):
        mean_ratio = np.mean(stutter_ratios[name])
        ax.annotate(f'Mean: {mean_ratio:.1%}',
                    xy=(i + 1, mean_ratio),
                    xytext=(10, 0),
                    textcoords='offset points',
                    fontsize=9,
                    ha='left')

    plt.tight_layout()
    return fig


# ============================================================================
# Summary Table Generation
# ============================================================================

def generate_summary_table(
    result: "TraceVerificationResult",
) -> str:
    """
    Generate a markdown summary table for verification results.

    Args:
        result: Verification result

    Returns:
        Markdown formatted table string
    """
    lines = []
    lines.append("| Model | Raw Trace (mean) | NS Trace (mean) | Stutter Ratio | Status |")
    lines.append("|-------|------------------|-----------------|---------------|--------|")

    model_names = list(result.model_stats.keys())

    for name in model_names:
        stats = result.model_stats[name]
        raw = stats.get('avg_raw_length', stats.get('raw_length', 0))
        ns = stats.get('avg_ns_length', stats.get('ns_length', 0))
        stutter_ratio = (raw - ns) / raw if raw > 0 else 0

        status = "Equivalent" if result.is_equivalent else "Not Equivalent"

        lines.append(f"| {name} | {raw:.1f} | {ns:.1f} | {stutter_ratio:.1%} | {status} |")

    return "\n".join(lines)


def print_verification_summary(result: "TraceVerificationResult") -> None:
    """
    Print a formatted summary of verification results to console.

    Args:
        result: Verification result
    """
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    print(f"\nStatus: {'EQUIVALENT' if result.is_equivalent else 'NOT EQUIVALENT'}")
    print(f"Time elapsed: {result.time_elapsed:.2f}s")

    if hasattr(result, 'num_seeds') and result.num_seeds > 1:
        print(f"Seeds verified: {result.equivalent_count}/{result.num_seeds}")

    print("\nModel Statistics:")
    print("-" * 50)

    model_names = list(result.model_stats.keys())
    for name in model_names:
        stats = result.model_stats[name]
        raw = stats.get('avg_raw_length', stats.get('raw_length', 0))
        ns = stats.get('avg_ns_length', stats.get('ns_length', 0))
        stutter_ratio = (raw - ns) / raw if raw > 0 else 0

        print(f"  {name}:")
        print(f"    Raw trace length:       {raw:.1f}")
        print(f"    No-stutter length:      {ns:.1f}")
        print(f"    Stutter ratio:          {stutter_ratio:.1%}")

    print("\n" + "=" * 70)
