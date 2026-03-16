"""
verification/trace_plotting.py

Timeseries trace visualization for SimASM stutter equivalence verification.

Provides:
- TimeseriesPlotConfig: Configuration for timeseries plot appearance
- plot_trace_comparison_grid: Create N×2 grid comparing raw and no-stutter traces
- plot_single_trace_comparison: Plot single raw vs no-stutter comparison

Usage:
    from simasm.verification.trace_plotting import (
        plot_trace_comparison_grid,
        TimeseriesPlotConfig,
    )

    fig = plot_trace_comparison_grid(
        eg_traces={0: trace_0, 10: trace_10},
        acd_traces={0: trace_0, 10: trace_10},
        seeds=[0, 10],
        output_path=Path("warehouse_traces.png"),
    )
"""

from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
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
        except Exception:
            try:
                matplotlib.use('Qt5Agg')
            except Exception:
                matplotlib.use('Agg')
    else:
        matplotlib.use('Agg')

import matplotlib.pyplot as plt
import numpy as np

from simasm.log.logger import get_logger

if TYPE_CHECKING:
    from simasm.verification.numeric_trace import NumericTrace

logger = get_logger(__name__)


@dataclass
class TimeseriesPlotConfig:
    """Configuration for timeseries plot generation."""
    figsize: Tuple[int, int] = (14, 18)
    dpi: int = 300
    color_eg: str = '#2E86AB'  # Blue
    color_acd: str = '#A23B72'  # Magenta/Pink
    linewidth_eg: float = 1.5
    linewidth_acd: float = 1.5
    linestyle_eg: str = '-'
    linestyle_acd: str = '--'
    alpha: float = 0.9
    show_grid: bool = True
    grid_alpha: float = 0.3
    title_fontsize: int = 10
    label_fontsize: int = 9
    tick_fontsize: int = 8
    legend_fontsize: int = 8
    y_label: str = "Total Busy Servers"
    x_label: str = "Simulation Time"
    y_min: Optional[float] = None
    y_max: Optional[float] = None


def plot_trace_comparison_grid(
    eg_traces: Dict[int, "NumericTrace"],
    acd_traces: Dict[int, "NumericTrace"],
    seeds: List[int],
    output_path: Optional[Path] = None,
    title: str = "Observable State Trajectory",
    show_raw: bool = True,
    show_no_stutter: bool = True,
    config: Optional[TimeseriesPlotConfig] = None,
    eg_label: str = "Event Graph",
    acd_label: str = "Activity Cycle Diagram",
) -> plt.Figure:
    """
    Create N×2 grid of timeseries plots comparing EG and ACD traces.

    Layout:
    - Rows: One per seed
    - Left column: Raw traces (EG solid blue, ACD dashed magenta)
    - Right column: No-stutter traces

    Args:
        eg_traces: Dict mapping seed -> NumericTrace for Event Graph model
        acd_traces: Dict mapping seed -> NumericTrace for ACD model
        seeds: List of seeds to display (determines row order)
        output_path: Path to save figure (optional)
        title: Main figure title
        show_raw: Whether to include raw trace column
        show_no_stutter: Whether to include no-stutter trace column
        config: Plot configuration (uses defaults if None)
        eg_label: Label for Event Graph model in legend
        acd_label: Label for ACD model in legend

    Returns:
        Matplotlib figure
    """
    if config is None:
        config = TimeseriesPlotConfig()

    # Determine grid dimensions
    n_rows = len(seeds)
    n_cols = int(show_raw) + int(show_no_stutter)

    if n_cols == 0:
        raise ValueError("At least one of show_raw or show_no_stutter must be True")

    # Adjust figure size based on rows
    figsize = (config.figsize[0], 3 * n_rows)

    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=figsize,
        sharex=False,
        sharey=True,
        squeeze=False,
    )

    # Main title
    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.995)

    # Column headers
    col_titles = []
    if show_raw:
        col_titles.append("Raw Traces")
    if show_no_stutter:
        col_titles.append("No-Stutter Traces")

    for col_idx, col_title in enumerate(col_titles):
        axes[0, col_idx].set_title(col_title, fontsize=config.title_fontsize + 2, pad=10)

    # Plot each seed row
    for row_idx, seed in enumerate(seeds):
        eg_trace = eg_traces.get(seed)
        acd_trace = acd_traces.get(seed)

        if eg_trace is None or acd_trace is None:
            logger.warning(f"Missing trace for seed {seed}")
            continue

        col_idx = 0

        # Raw traces column
        if show_raw:
            ax = axes[row_idx, col_idx]
            plot_single_trace_comparison(
                ax=ax,
                eg_trace=eg_trace,
                acd_trace=acd_trace,
                config=config,
                eg_label=eg_label if row_idx == 0 else None,
                acd_label=acd_label if row_idx == 0 else None,
                show_legend=(row_idx == 0),
            )
            ax.set_ylabel(f"Seed {seed}\n{config.y_label}", fontsize=config.label_fontsize)
            col_idx += 1

        # No-stutter traces column
        if show_no_stutter:
            ax = axes[row_idx, col_idx]
            eg_ns = eg_trace.no_stutter_trace()
            acd_ns = acd_trace.no_stutter_trace()

            plot_single_trace_comparison(
                ax=ax,
                eg_trace=eg_ns,
                acd_trace=acd_ns,
                config=config,
                eg_label=eg_label if row_idx == 0 and not show_raw else None,
                acd_label=acd_label if row_idx == 0 and not show_raw else None,
                show_legend=(row_idx == 0 and not show_raw),
            )

            if not show_raw:
                ax.set_ylabel(f"Seed {seed}\n{config.y_label}", fontsize=config.label_fontsize)
            else:
                ax.set_ylabel("")

            # Add annotation for perfect overlap
            ns_overlap = _traces_overlap(eg_ns, acd_ns)
            if ns_overlap:
                ax.annotate(
                    "Traces overlap perfectly\n(stutter equivalence)",
                    xy=(0.98, 0.95),
                    xycoords='axes fraction',
                    fontsize=7,
                    ha='right',
                    va='top',
                    color='green',
                    style='italic',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow',
                              edgecolor='green', alpha=0.8),
                )

    # Set x-labels on bottom row only
    for col_idx in range(n_cols):
        axes[-1, col_idx].set_xlabel(config.x_label, fontsize=config.label_fontsize)

    # Apply y-limits if specified
    if config.y_min is not None or config.y_max is not None:
        for ax_row in axes:
            for ax in ax_row:
                if config.y_min is not None:
                    ax.set_ylim(bottom=config.y_min)
                if config.y_max is not None:
                    ax.set_ylim(top=config.y_max)

    # Add legend to top-left subplot
    if show_raw:
        handles, labels = axes[0, 0].get_legend_handles_labels()
        if handles:
            fig.legend(
                handles, labels,
                loc='upper right',
                bbox_to_anchor=(0.99, 0.99),
                fontsize=config.legend_fontsize,
                framealpha=0.9,
            )

    plt.tight_layout(rect=[0, 0, 1, 0.98])

    # Save if path provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=config.dpi, bbox_inches='tight')
        logger.info(f"Saved timeseries plot to {output_path}")

    return fig


def plot_single_trace_comparison(
    ax: plt.Axes,
    eg_trace: "NumericTrace",
    acd_trace: "NumericTrace",
    config: TimeseriesPlotConfig,
    eg_label: Optional[str] = None,
    acd_label: Optional[str] = None,
    show_legend: bool = False,
) -> None:
    """
    Plot single raw vs no-stutter comparison on an axis.

    Uses step plots (where='post') for proper discrete-event visualization.

    Args:
        ax: Matplotlib axis to plot on
        eg_trace: Event Graph numeric trace
        acd_trace: ACD numeric trace
        config: Plot configuration
        eg_label: Label for EG trace (None to skip legend entry)
        acd_label: Label for ACD trace (None to skip legend entry)
        show_legend: Whether to show legend on this axis
    """
    # Plot EG trace (solid line, drawn second so it's on top)
    eg_times = eg_trace.times
    eg_values = eg_trace.values

    # Plot ACD trace first (dashed line, underneath)
    acd_times = acd_trace.times
    acd_values = acd_trace.values

    # Use step plot for discrete-event visualization
    ax.step(
        acd_times, acd_values,
        where='post',
        color=config.color_acd,
        linewidth=config.linewidth_acd,
        linestyle=config.linestyle_acd,
        alpha=config.alpha,
        label=acd_label,
    )

    ax.step(
        eg_times, eg_values,
        where='post',
        color=config.color_eg,
        linewidth=config.linewidth_eg,
        linestyle=config.linestyle_eg,
        alpha=config.alpha,
        label=eg_label,
    )

    # Grid
    if config.show_grid:
        ax.grid(True, alpha=config.grid_alpha)

    # Tick font size
    ax.tick_params(axis='both', labelsize=config.tick_fontsize)

    # Legend
    if show_legend:
        ax.legend(fontsize=config.legend_fontsize, loc='upper right')


def _traces_overlap(trace_a: "NumericTrace", trace_b: "NumericTrace") -> bool:
    """
    Check if two traces overlap (same times and values).

    Args:
        trace_a: First trace
        trace_b: Second trace

    Returns:
        True if traces have identical points
    """
    if len(trace_a) != len(trace_b):
        return False

    for (t_a, v_a), (t_b, v_b) in zip(trace_a, trace_b):
        if v_a != v_b:
            return False
        if abs(t_a - t_b) > 1e-9:
            return False

    return True


def plot_timeseries_with_annotations(
    eg_trace: "NumericTrace",
    acd_trace: "NumericTrace",
    seed: int,
    output_path: Optional[Path] = None,
    config: Optional[TimeseriesPlotConfig] = None,
    title: Optional[str] = None,
    eg_label: str = "Event Graph",
    acd_label: str = "Activity Cycle Diagram",
) -> plt.Figure:
    """
    Create a single publication-ready timeseries plot with annotations.

    Similar to the reference timeseries_trace.png style.

    Args:
        eg_trace: Event Graph numeric trace
        acd_trace: ACD numeric trace
        seed: Random seed used
        output_path: Path to save figure (optional)
        config: Plot configuration (uses defaults if None)
        title: Plot title (defaults to "Observable State Trajectory (Seed N)")
        eg_label: Label for EG model
        acd_label: Label for ACD model

    Returns:
        Matplotlib figure
    """
    if config is None:
        config = TimeseriesPlotConfig()

    fig, ax = plt.subplots(figsize=(12, 4), dpi=config.dpi)

    # Default title
    if title is None:
        title = f"Observable State Trajectory (Seed {seed})"

    ax.set_title(title, fontsize=12, fontweight='bold')

    # Get no-stutter traces
    eg_ns = eg_trace.no_stutter_trace()
    acd_ns = acd_trace.no_stutter_trace()

    # Plot no-stutter traces (they should overlap)
    ax.step(
        acd_ns.times, acd_ns.values,
        where='post',
        color=config.color_acd,
        linewidth=config.linewidth_acd,
        linestyle=config.linestyle_acd,
        alpha=config.alpha,
        label=acd_label,
    )

    ax.step(
        eg_ns.times, eg_ns.values,
        where='post',
        color=config.color_eg,
        linewidth=config.linewidth_eg,
        linestyle=config.linestyle_eg,
        alpha=config.alpha,
        label=eg_label,
    )

    # Labels
    ax.set_xlabel(config.x_label, fontsize=config.label_fontsize)
    ax.set_ylabel(config.y_label, fontsize=config.label_fontsize)

    # Grid
    if config.show_grid:
        ax.grid(True, alpha=config.grid_alpha)

    # Y-limits
    if config.y_min is not None:
        ax.set_ylim(bottom=config.y_min)
    if config.y_max is not None:
        ax.set_ylim(top=config.y_max)

    # Legend
    ax.legend(fontsize=config.legend_fontsize, loc='upper right')

    # Add annotation if traces overlap
    if _traces_overlap(eg_ns, acd_ns):
        # Add shaded region to highlight overlap
        times = eg_ns.times
        if len(times) > 2:
            mid_start = len(times) // 3
            mid_end = 2 * len(times) // 3
            t_start = times[mid_start]
            t_end = times[mid_end]
            ax.axvspan(t_start, t_end, alpha=0.15, color='green')

            # Annotation box
            ax.annotate(
                "Traces overlap perfectly\n(stutter equivalence)",
                xy=(0.98, 0.95),
                xycoords='axes fraction',
                fontsize=9,
                ha='right',
                va='top',
                color='green',
                style='italic',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow',
                          edgecolor='green', alpha=0.8),
            )

            # Add "Same state transitions at same times" annotation
            mid_t = (t_start + t_end) / 2
            mid_idx = min(mid_start + (mid_end - mid_start) // 2, len(eg_ns.values) - 1)
            mid_v = eg_ns.values[mid_idx] if mid_idx < len(eg_ns.values) else 0
            ax.annotate(
                "Same state transitions\nat same times",
                xy=(mid_t, mid_v),
                xytext=(mid_t, mid_v - 1.5),
                fontsize=8,
                ha='center',
                va='top',
                color='darkgreen',
            )

    plt.tight_layout()

    # Save if path provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=config.dpi, bbox_inches='tight')
        logger.info(f"Saved annotated timeseries plot to {output_path}")

    return fig
