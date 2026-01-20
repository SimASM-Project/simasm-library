"""
simulation/plotting.py

Automatic visualization generation for SimASM experiments.

Provides:
- PlotConfig: Configuration for plot appearance
- generate_experiment_plots: Main entry point for plot generation
- Individual plotting functions for different chart types

Usage:
    from simasm.simulation.plotting import generate_experiment_plots

    generate_experiment_plots(
        result=experiment_result,
        output_dir=Path("output/2026-01-09_14-23-45_MyExperiment"),
        in_notebook=False
    )
"""

from typing import Optional, Tuple, List, Dict, Any
from pathlib import Path
from dataclasses import dataclass
import sys
import os

# Check if we're in a notebook environment BEFORE any matplotlib imports
_in_notebook = 'ipykernel' in sys.modules or os.environ.get('MPLBACKEND', '').startswith('module://')

# Set matplotlib backend BEFORE importing pyplot
import matplotlib
if not _in_notebook:
    # For CLI/scripts, use an interactive backend
    # Try to use TkAgg, fall back to Agg if no display available
    if os.environ.get('DISPLAY', '') or sys.platform == 'win32':
        try:
            matplotlib.use('TkAgg')
        except:
            try:
                matplotlib.use('Qt5Agg')
            except:
                matplotlib.use('Agg')  # Non-interactive fallback
    else:
        matplotlib.use('Agg')  # No display available

import matplotlib.pyplot as plt
# Enable interactive mode for CLI (doesn't affect notebooks)
if not _in_notebook:
    plt.ion()  # Turn on interactive mode
import numpy as np
from scipy import stats as scipy_stats

from simasm.log.logger import get_logger
from .runner import ExperimentResult, ReplicationResult

logger = get_logger(__name__)


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class PlotConfig:
    """Configuration for plot generation."""
    dpi: int = 150
    figsize_summary: Tuple[int, int] = (10, 6)
    figsize_boxplot: Tuple[int, int] = (10, 6)
    figsize_timeseries_per_stat: Tuple[int, int] = (10, 3)
    show_grid: bool = True
    color_mean: str = '#2E86AB'
    color_ci: str = '#A23B72'
    color_warmup: str = '#FF6B6B'
    alpha_ci: float = 0.3
    alpha_bar: float = 0.7


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
    """
    Configure matplotlib for the current environment.

    Note: Backend is set at module import time. This function
    only configures notebook-specific settings if needed.
    """
    if in_notebook:
        # Configure inline display for Jupyter
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

def generate_experiment_plots(
    result: ExperimentResult,
    output_dir: Path,
    plot_config: Optional[PlotConfig] = None,
    in_notebook: Optional[bool] = None
) -> None:
    """
    Generate all plots for an experiment.

    Creates three PNG files:
    - summary_statistics.png: Bar chart of means with 95% CI
    - boxplots.png: Box plots showing distribution across replications
    - timeseries.png: Time series plots for traced statistics (if any)

    Args:
        result: Experiment result object
        output_dir: Directory to save plots (must exist)
        plot_config: Plotting configuration (uses defaults if None)
        in_notebook: True if in Jupyter, False if CLI/API, None=auto-detect
    """
    if plot_config is None:
        plot_config = PlotConfig()

    # Auto-detect environment if not specified
    if in_notebook is None:
        in_notebook = _is_notebook()

    # Set up matplotlib backend
    _setup_matplotlib_backend(in_notebook)

    logger.info(f"Generating plots for experiment '{result.config.name}'")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Environment: {'Jupyter notebook' if in_notebook else 'CLI/API'}")
    logger.info(f"Matplotlib backend: {matplotlib.get_backend()}")

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect all figures before displaying
    figures = []

    # 1. Summary statistics bar chart
    try:
        fig_summary = plot_summary_statistics(result, plot_config)
        fig_summary.savefig(output_dir / "summary_statistics.png", dpi=plot_config.dpi, bbox_inches='tight')
        figures.append(fig_summary)
        logger.info("Generated summary_statistics.png")
    except Exception as e:
        logger.error(f"Failed to generate summary statistics plot: {e}")

    # 2. Box plots
    try:
        fig_box = plot_boxplots(result, plot_config)
        fig_box.savefig(output_dir / "boxplots.png", dpi=plot_config.dpi, bbox_inches='tight')
        figures.append(fig_box)
        logger.info("Generated boxplots.png")
    except Exception as e:
        logger.error(f"Failed to generate box plots: {e}")

    # 3. Time series (if traces exist)
    if has_traces(result):
        try:
            fig_ts = plot_time_series(result, plot_config)
            fig_ts.savefig(output_dir / "timeseries.png", dpi=plot_config.dpi, bbox_inches='tight')
            figures.append(fig_ts)
            logger.info("Generated timeseries.png")
        except Exception as e:
            logger.error(f"Failed to generate time series plots: {e}")
    else:
        logger.info("No traced statistics found, skipping time series plot")

    # Display all figures at once
    if in_notebook:
        # In Jupyter, show inline
        for fig in figures:
            plt.figure(fig.number)
            plt.show()
    else:
        # In CLI, show all windows and block until user closes them
        if figures:
            print(f"\n{'='*70}")
            print(f"PLOTS GENERATED - {len(figures)} window(s) should appear")
            print(f"{'='*70}")
            print(f"Files saved to: {output_dir}")
            print(f"")
            print(f"If windows don't appear, the plots have been saved as PNG files.")
            print(f"Press Ctrl+C to skip waiting for windows and continue.")
            print(f"{'='*70}\n")

            # Explicitly show each figure to create the windows
            for fig in figures:
                fig.show()

            # Force window drawing
            try:
                plt.pause(0.5)  # Longer pause to ensure windows fully render
            except:
                pass

            try:
                # Try to bring windows to front (may not work on all backends/platforms)
                for fig in figures:
                    try:
                        # For Tk backend
                        if hasattr(fig.canvas.manager, 'window'):
                            fig.canvas.manager.window.attributes('-topmost', True)
                            fig.canvas.manager.window.attributes('-topmost', False)
                    except:
                        pass
            except:
                pass

            try:
                plt.show(block=True)
            except KeyboardInterrupt:
                print("\nSkipping plot display...")

    # Clean up
    for fig in figures:
        plt.close(fig)

    logger.info("Plot generation complete")


# ============================================================================
# Plot Functions
# ============================================================================

def plot_summary_statistics(result: ExperimentResult, config: PlotConfig) -> plt.Figure:
    """
    Create horizontal bar chart of mean ± 95% CI for all statistics.

    Args:
        result: Experiment result
        config: Plot configuration

    Returns:
        Matplotlib figure
    """
    fig, ax = plt.subplots(figsize=config.figsize_summary)

    stat_names = list(result.summary.keys())
    if not stat_names:
        ax.text(0.5, 0.5, 'No statistics to display',
                ha='center', va='center', transform=ax.transAxes)
        return fig

    means = [result.summary[name].mean for name in stat_names]
    ci_lower = [result.summary[name].ci_lower for name in stat_names]
    ci_upper = [result.summary[name].ci_upper for name in stat_names]

    # Error bar widths (from mean to CI bounds)
    xerr_lower = [means[i] - ci_lower[i] for i in range(len(means))]
    xerr_upper = [ci_upper[i] - means[i] for i in range(len(means))]

    y_pos = np.arange(len(stat_names))

    # Plot bars
    ax.barh(y_pos, means, color=config.color_mean, alpha=config.alpha_bar, label='Mean')

    # Plot error bars
    ax.errorbar(means, y_pos, xerr=[xerr_lower, xerr_upper],
                fmt='none', ecolor=config.color_ci, capsize=5,
                linewidth=2, label='95% CI')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(stat_names)
    ax.set_xlabel('Value')
    ax.set_title(f'Summary Statistics: {result.config.name}\n'
                 f'({result.num_replications} replications)', fontsize=12, fontweight='bold')
    ax.grid(config.show_grid, axis='x', alpha=0.3)
    ax.legend(loc='best')

    plt.tight_layout()
    return fig


def plot_boxplots(result: ExperimentResult, config: PlotConfig) -> plt.Figure:
    """
    Create box plots showing distribution of each statistic across replications.

    Args:
        result: Experiment result
        config: Plot configuration

    Returns:
        Matplotlib figure
    """
    fig, ax = plt.subplots(figsize=config.figsize_boxplot)

    stat_names = list(result.summary.keys())
    if not stat_names:
        ax.text(0.5, 0.5, 'No statistics to display',
                ha='center', va='center', transform=ax.transAxes)
        return fig

    data = []
    for name in stat_names:
        values = [rep.statistics[name] for rep in result.replications
                  if name in rep.statistics]
        data.append(values)

    bp = ax.boxplot(data, labels=stat_names, patch_artist=True)

    # Style boxes
    for patch in bp['boxes']:
        patch.set_facecolor(config.color_mean)
        patch.set_alpha(0.6)

    ax.set_ylabel('Value')
    ax.set_title(f'Distribution Across Replications: {result.config.name}',
                 fontsize=12, fontweight='bold')
    ax.grid(config.show_grid, axis='y', alpha=0.3)
    plt.xticks(rotation=45, ha='right')

    plt.tight_layout()
    return fig


def plot_time_series(result: ExperimentResult, config: PlotConfig) -> plt.Figure:
    """
    Create time series plots with mean trace and confidence bands.

    One subplot per traced statistic.

    Args:
        result: Experiment result
        config: Plot configuration

    Returns:
        Matplotlib figure
    """
    # Get list of statistics with traces
    traced_stats = get_traced_statistics(result)

    if not traced_stats:
        fig, ax = plt.subplots(figsize=config.figsize_timeseries_per_stat)
        ax.text(0.5, 0.5, 'No traced statistics to display',
                ha='center', va='center', transform=ax.transAxes)
        return fig

    n_stats = len(traced_stats)
    fig, axes = plt.subplots(n_stats, 1,
                            figsize=(config.figsize_timeseries_per_stat[0],
                                    config.figsize_timeseries_per_stat[1] * n_stats),
                            sharex=True)

    if n_stats == 1:
        axes = [axes]

    warmup_time = result.config.replications.warmup
    end_time = result.config.replications.length

    for ax, stat_name in zip(axes, traced_stats):
        # Aggregate traces across replications
        times, means, (ci_lower, ci_upper) = aggregate_traces(
            result.replications, stat_name, warmup_time, end_time
        )

        # Plot mean trace
        ax.plot(times, means, color=config.color_mean, linewidth=2, label='Mean')

        # Plot confidence band
        ax.fill_between(times, ci_lower, ci_upper,
                       color=config.color_ci, alpha=config.alpha_ci, label='95% CI')

        # Mark warmup period end
        if warmup_time > 0:
            ax.axvline(warmup_time, color=config.color_warmup,
                      linestyle='--', alpha=0.7, linewidth=1.5, label='Warmup End')

        ax.set_ylabel(stat_name)
        ax.grid(config.show_grid, alpha=0.3)
        ax.legend(loc='best', fontsize=9)

    axes[-1].set_xlabel('Simulation Time')
    fig.suptitle(f'Time Series: {result.config.name}',
                 fontsize=14, fontweight='bold')
    plt.tight_layout()

    return fig


# ============================================================================
# Helper Functions
# ============================================================================

def has_traces(result: ExperimentResult) -> bool:
    """
    Check if any replication has trace data.

    Args:
        result: Experiment result

    Returns:
        True if traces exist
    """
    if not result.replications:
        return False

    for rep in result.replications:
        if rep.traces:
            return True
    return False


def get_traced_statistics(result: ExperimentResult) -> List[str]:
    """
    Get list of statistic names that have trace data.

    Args:
        result: Experiment result

    Returns:
        List of statistic names with traces
    """
    if not result.replications:
        return []

    # Get traced stats from first replication
    first_rep = result.replications[0]
    return list(first_rep.traces.keys())


def aggregate_traces(
    replications: List[ReplicationResult],
    stat_name: str,
    warmup_time: float,
    end_time: float,
    num_points: int = 1000,
    max_points: int = 10000
) -> Tuple[np.ndarray, np.ndarray, Tuple[np.ndarray, np.ndarray]]:
    """
    Aggregate trace data across replications.

    Interpolates each replication's trace to a common time grid,
    then computes mean and 95% confidence intervals at each point.

    Args:
        replications: List of replication results
        stat_name: Name of statistic to aggregate
        warmup_time: Warmup period
        end_time: Simulation end time
        num_points: Number of points in output grid
        max_points: Maximum number of points (auto-downsample if exceeded)

    Returns:
        Tuple of (times, means, (ci_lower, ci_upper))
    """
    # Collect traces from all replications
    traces_list = []
    for rep in replications:
        trace = rep.get_trace(stat_name)
        if trace and len(trace) > 0:
            traces_list.append(trace)

    if not traces_list:
        # No traces found, return empty arrays
        return np.array([]), np.array([]), (np.array([]), np.array([]))

    # Check if we need to downsample
    max_trace_len = max(len(t) for t in traces_list)
    if max_trace_len > max_points:
        num_points = min(num_points, max_points)
        logger.warning(f"Trace has {max_trace_len} points, downsampling to {num_points}")

    # Create common time grid
    times = np.linspace(warmup_time, end_time, num_points)

    # Interpolate each replication to common grid
    interp_values = []
    for trace in traces_list:
        if len(trace) < 2:
            # Skip traces with insufficient data
            continue

        t_vals, y_vals = zip(*trace)
        t_vals = np.array(t_vals)
        y_vals = np.array(y_vals)

        # Interpolate
        interp = np.interp(times, t_vals, y_vals)
        interp_values.append(interp)

    if not interp_values:
        return np.array([]), np.array([]), (np.array([]), np.array([]))

    # Compute statistics at each time point
    interp_array = np.array(interp_values)  # Shape: (n_reps, n_points)
    n_reps = len(interp_values)

    means = np.mean(interp_array, axis=0)
    stds = np.std(interp_array, axis=0, ddof=1)

    # 95% CI: mean ± t_alpha * std / sqrt(n)
    # Use t-distribution for small sample sizes
    if n_reps > 1:
        t_alpha = scipy_stats.t.ppf(0.975, n_reps - 1)
        ci_width = t_alpha * stds / np.sqrt(n_reps)
        ci_lower = means - ci_width
        ci_upper = means + ci_width
    else:
        # Single replication, no CI
        ci_lower = means
        ci_upper = means

    return times, means, (ci_lower, ci_upper)
