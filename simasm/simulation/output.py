"""
simulation/output.py

Output formatters for experiment results.

Provides:
- OutputFormatter: Abstract base class for formatters
- JSONFormatter: JSON output format
- CSVFormatter: CSV output format
- ConsoleFormatter: Human-readable console output
- MarkdownFormatter: Markdown table format

Usage:
    from simasm.simulation.output import JSONFormatter, CSVFormatter
    
    # Format result as JSON
    formatter = JSONFormatter()
    json_str = formatter.format(result)
    
    # Write to file
    formatter.write(result, "results.json")
    
    # Or use convenience functions
    from simasm.simulation.output import to_json, to_csv
    json_str = to_json(result)
    csv_str = to_csv(result)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TextIO, Optional, List, Dict, Any, Union
from pathlib import Path
from io import StringIO
import json
import csv

from simasm.log.logger import get_logger

from .runner import ExperimentResult, ReplicationResult, SummaryStatistics

logger = get_logger(__name__)


# ============================================================================
# Output Configuration
# ============================================================================

@dataclass
class OutputConfig:
    """
    Configuration for output formatting.
    
    Attributes:
        include_replications: Include per-replication data
        include_summary: Include summary statistics
        include_config: Include experiment configuration
        include_metadata: Include metadata (timestamps, versions)
        decimal_places: Number of decimal places for floats
        time_series_format: How to handle time series ('full', 'summary', 'omit')
    """
    include_replications: bool = True
    include_summary: bool = True
    include_config: bool = False
    include_metadata: bool = True
    decimal_places: int = 4
    time_series_format: str = "summary"  # 'full', 'summary', 'omit'


# ============================================================================
# Abstract Base Class
# ============================================================================

class OutputFormatter(ABC):
    """
    Abstract base class for output formatters.
    
    Subclasses implement format() to produce specific output formats.
    """
    
    def __init__(self, config: Optional[OutputConfig] = None):
        """
        Create formatter.
        
        Args:
            config: Output configuration (uses defaults if None)
        """
        self.config = config or OutputConfig()
    
    @abstractmethod
    def format(self, result: ExperimentResult) -> str:
        """
        Format experiment result as string.
        
        Args:
            result: Experiment result to format
        
        Returns:
            Formatted string
        """
        ...
    
    def write(self, result: ExperimentResult, file_path: Union[str, Path]) -> None:
        """
        Write formatted result to file.
        
        Args:
            result: Experiment result
            file_path: Output file path
        """
        path = Path(file_path)
        content = self.format(result)
        path.write_text(content)
        logger.info(f"Wrote results to {path}")
    
    def _format_float(self, value: float) -> str:
        """Format float with configured decimal places."""
        return f"{value:.{self.config.decimal_places}f}"
    
    def _format_value(self, value: Any) -> Any:
        """Format a value for output."""
        if isinstance(value, float):
            return round(value, self.config.decimal_places)
        elif isinstance(value, list):
            if self.config.time_series_format == "omit":
                return None
            elif self.config.time_series_format == "summary":
                return f"[{len(value)} points]"
            else:
                return value
        return value


# ============================================================================
# JSON Formatter
# ============================================================================

class JSONFormatter(OutputFormatter):
    """
    JSON output formatter.
    
    Produces structured JSON suitable for programmatic consumption.
    
    Example output:
        {
            "experiment": "MM1 Queue",
            "replications": [...],
            "summary": {...},
            "metadata": {...}
        }
    """
    
    def __init__(
        self, 
        config: Optional[OutputConfig] = None,
        indent: int = 2,
        sort_keys: bool = False,
    ):
        """
        Create JSON formatter.
        
        Args:
            config: Output configuration
            indent: JSON indentation (None for compact)
            sort_keys: Sort dictionary keys
        """
        super().__init__(config)
        self.indent = indent
        self.sort_keys = sort_keys
    
    def format(self, result: ExperimentResult) -> str:
        """Format result as JSON string."""
        data: Dict[str, Any] = {}
        
        # Experiment name
        exp_config = result.config
        data["experiment"] = exp_config.name or "Unnamed Experiment"
        
        # Metadata
        if self.config.include_metadata:
            import datetime
            data["metadata"] = {
                "num_replications": result.num_replications,
                "total_wall_time": round(result.total_wall_time, 3),
                "generated_at": datetime.datetime.now().isoformat(),
            }
        
        # Configuration
        if self.config.include_config:
            data["config"] = {
                "run_length": exp_config.replications.length,
                "warmup": exp_config.replications.warmup,
                "base_seed": exp_config.replications.base_seed,
            }
        
        # Replications
        if self.config.include_replications:
            data["replications"] = []
            for rep in result.replications:
                rep_data = {
                    "id": rep.replication_id,
                    "seed": rep.seed,
                    "final_time": round(rep.final_time, self.config.decimal_places),
                    "steps_taken": rep.steps_taken,
                    "wall_time": round(rep.wall_time, self.config.decimal_places),
                    "statistics": {}
                }
                
                for name, value in rep.statistics.items():
                    formatted = self._format_value(value)
                    if formatted is not None:
                        rep_data["statistics"][name] = formatted
                
                data["replications"].append(rep_data)
        
        # Summary
        if self.config.include_summary:
            data["summary"] = {}
            for name, summ in result.summary.items():
                data["summary"][name] = {
                    "mean": round(summ.mean, self.config.decimal_places),
                    "std_dev": round(summ.std_dev, self.config.decimal_places),
                    "min": round(summ.min_val, self.config.decimal_places),
                    "max": round(summ.max_val, self.config.decimal_places),
                    "ci_95": [
                        round(summ.ci_lower, self.config.decimal_places),
                        round(summ.ci_upper, self.config.decimal_places),
                    ],
                    "n": summ.n,
                }
        
        return json.dumps(data, indent=self.indent, sort_keys=self.sort_keys)


# ============================================================================
# CSV Formatter
# ============================================================================

class CSVFormatter(OutputFormatter):
    """
    CSV output formatter.
    
    Produces CSV suitable for import into spreadsheets or data tools.
    
    Sections:
    - Replications: One row per replication
    - Summary: Aggregated statistics
    """
    
    def __init__(
        self, 
        config: Optional[OutputConfig] = None,
        delimiter: str = ",",
        include_header: bool = True,
    ):
        """
        Create CSV formatter.
        
        Args:
            config: Output configuration
            delimiter: Field delimiter
            include_header: Include header row
        """
        super().__init__(config)
        self.delimiter = delimiter
        self.include_header = include_header
    
    def format(self, result: ExperimentResult) -> str:
        """Format result as CSV string."""
        output = StringIO()
        writer = csv.writer(output, delimiter=self.delimiter)
        
        # Replications section
        if self.config.include_replications and result.replications:
            output.write("# Replications\n")
            
            # Get statistic names from first replication
            stat_names = list(result.replications[0].statistics.keys())
            
            # Filter out time series if configured
            if self.config.time_series_format == "omit":
                stat_names = [
                    name for name in stat_names
                    if not isinstance(result.replications[0].statistics[name], list)
                ]
            
            # Header
            if self.include_header:
                header = ["rep_id", "seed", "final_time", "steps", "wall_time"] + stat_names
                writer.writerow(header)
            
            # Data rows
            for rep in result.replications:
                row = [
                    rep.replication_id,
                    rep.seed,
                    self._format_float(rep.final_time),
                    rep.steps_taken,
                    self._format_float(rep.wall_time),
                ]
                
                for name in stat_names:
                    value = rep.statistics.get(name)
                    formatted = self._format_value(value)
                    row.append(formatted if formatted is not None else "")
                
                writer.writerow(row)
        
        # Summary section
        if self.config.include_summary and result.summary:
            output.write("\n# Summary\n")
            
            if self.include_header:
                writer.writerow([
                    "statistic", "mean", "std_dev", "min", "max",
                    "ci_lower", "ci_upper", "n"
                ])
            
            for name, summ in result.summary.items():
                writer.writerow([
                    name,
                    self._format_float(summ.mean),
                    self._format_float(summ.std_dev),
                    self._format_float(summ.min_val),
                    self._format_float(summ.max_val),
                    self._format_float(summ.ci_lower),
                    self._format_float(summ.ci_upper),
                    summ.n,
                ])
        
        return output.getvalue()


# ============================================================================
# Console Formatter
# ============================================================================

class ConsoleFormatter(OutputFormatter):
    """
    Human-readable console output formatter.
    
    Produces formatted text suitable for terminal display.
    """
    
    def __init__(
        self, 
        config: Optional[OutputConfig] = None,
        width: int = 70,
    ):
        """
        Create console formatter.
        
        Args:
            config: Output configuration
            width: Maximum line width
        """
        super().__init__(config)
        self.width = width
    
    def format(self, result: ExperimentResult) -> str:
        """Format result as human-readable text."""
        lines: List[str] = []
        
        # Header
        exp_name = result.config.name or "Simulation Experiment"
        lines.append("=" * self.width)
        lines.append(f"  {exp_name}")
        lines.append("=" * self.width)
        lines.append("")
        
        # Metadata
        if self.config.include_metadata:
            lines.append(f"Replications: {result.num_replications}")
            lines.append(f"Total wall time: {result.total_wall_time:.2f}s")
            lines.append(f"Run length: {result.config.replications.length}")
            lines.append(f"Warmup: {result.config.replications.warmup}")
            lines.append("")
        
        # Summary statistics
        if self.config.include_summary and result.summary:
            lines.append("Summary Statistics")
            lines.append("-" * self.width)
            
            # Find max name length for alignment
            max_name_len = max(len(name) for name in result.summary.keys())
            
            for name, summ in result.summary.items():
                mean_str = self._format_float(summ.mean)
                std_str = self._format_float(summ.std_dev)
                ci_low = self._format_float(summ.ci_lower)
                ci_high = self._format_float(summ.ci_upper)
                
                line = (
                    f"  {name:<{max_name_len}}  "
                    f"{mean_str:>12} ± {std_str:<10} "
                    f"(95% CI: [{ci_low}, {ci_high}])"
                )
                lines.append(line)
            
            lines.append("")
        
        # Per-replication data (brief)
        if self.config.include_replications and result.replications:
            lines.append("Per-Replication Results")
            lines.append("-" * self.width)
            
            # Show first few and last few if many replications
            n = len(result.replications)
            show_all = n <= 10
            
            def format_rep(rep: ReplicationResult) -> str:
                stats_str = ", ".join(
                    f"{k}={self._format_value(v)}"
                    for k, v in list(rep.statistics.items())[:3]
                )
                return f"  Rep {rep.replication_id:3d} (seed={rep.seed}): {stats_str}"
            
            if show_all:
                for rep in result.replications:
                    lines.append(format_rep(rep))
            else:
                for rep in result.replications[:3]:
                    lines.append(format_rep(rep))
                lines.append(f"  ... ({n - 6} more replications) ...")
                for rep in result.replications[-3:]:
                    lines.append(format_rep(rep))
            
            lines.append("")
        
        lines.append("=" * self.width)
        
        return "\n".join(lines)


# ============================================================================
# Markdown Formatter
# ============================================================================

class MarkdownFormatter(OutputFormatter):
    """
    Markdown table output formatter.
    
    Produces Markdown suitable for documentation or reports.
    """
    
    def format(self, result: ExperimentResult) -> str:
        """Format result as Markdown."""
        lines: List[str] = []
        
        # Title
        exp_name = result.config.name or "Simulation Results"
        lines.append(f"# {exp_name}")
        lines.append("")
        
        # Metadata
        if self.config.include_metadata:
            lines.append("## Experiment Info")
            lines.append("")
            lines.append(f"- **Replications:** {result.num_replications}")
            lines.append(f"- **Run length:** {result.config.replications.length}")
            lines.append(f"- **Warmup:** {result.config.replications.warmup}")
            lines.append(f"- **Wall time:** {result.total_wall_time:.2f}s")
            lines.append("")
        
        # Summary table
        if self.config.include_summary and result.summary:
            lines.append("## Summary Statistics")
            lines.append("")
            lines.append("| Statistic | Mean | Std Dev | 95% CI |")
            lines.append("|-----------|------|---------|--------|")
            
            for name, summ in result.summary.items():
                mean = self._format_float(summ.mean)
                std = self._format_float(summ.std_dev)
                ci = f"[{self._format_float(summ.ci_lower)}, {self._format_float(summ.ci_upper)}]"
                lines.append(f"| {name} | {mean} | {std} | {ci} |")
            
            lines.append("")
        
        # Replications table
        if self.config.include_replications and result.replications:
            lines.append("## Replication Data")
            lines.append("")
            
            # Get statistic names
            stat_names = list(result.replications[0].statistics.keys())
            
            # Filter time series
            if self.config.time_series_format == "omit":
                stat_names = [
                    name for name in stat_names
                    if not isinstance(result.replications[0].statistics[name], list)
                ]
            
            # Header
            header = "| Rep | Seed | " + " | ".join(stat_names) + " |"
            separator = "|-----|------|" + "|".join(["------"] * len(stat_names)) + "|"
            lines.append(header)
            lines.append(separator)
            
            # Limit rows for readability
            max_rows = 20
            reps_to_show = result.replications[:max_rows]
            
            for rep in reps_to_show:
                values = [str(self._format_value(rep.statistics.get(name, ""))) 
                          for name in stat_names]
                row = f"| {rep.replication_id} | {rep.seed} | " + " | ".join(values) + " |"
                lines.append(row)
            
            if len(result.replications) > max_rows:
                lines.append(f"| ... | ... | " + " | ".join(["..."] * len(stat_names)) + " |")
                lines.append(f"*({len(result.replications) - max_rows} more rows omitted)*")
            
            lines.append("")
        
        return "\n".join(lines)


# ============================================================================
# Convenience Functions
# ============================================================================

def to_json(
    result: ExperimentResult,
    include_replications: bool = True,
    include_summary: bool = True,
    indent: int = 2,
) -> str:
    """
    Format experiment result as JSON.
    
    Args:
        result: Experiment result
        include_replications: Include per-replication data
        include_summary: Include summary statistics
        indent: JSON indentation
    
    Returns:
        JSON string
    """
    config = OutputConfig(
        include_replications=include_replications,
        include_summary=include_summary,
    )
    formatter = JSONFormatter(config, indent=indent)
    return formatter.format(result)


def to_csv(
    result: ExperimentResult,
    include_replications: bool = True,
    include_summary: bool = True,
) -> str:
    """
    Format experiment result as CSV.
    
    Args:
        result: Experiment result
        include_replications: Include per-replication data
        include_summary: Include summary statistics
    
    Returns:
        CSV string
    """
    config = OutputConfig(
        include_replications=include_replications,
        include_summary=include_summary,
    )
    formatter = CSVFormatter(config)
    return formatter.format(result)


def to_console(result: ExperimentResult) -> str:
    """
    Format experiment result for console display.
    
    Args:
        result: Experiment result
    
    Returns:
        Human-readable string
    """
    formatter = ConsoleFormatter()
    return formatter.format(result)


def to_markdown(result: ExperimentResult) -> str:
    """
    Format experiment result as Markdown.
    
    Args:
        result: Experiment result
    
    Returns:
        Markdown string
    """
    formatter = MarkdownFormatter()
    return formatter.format(result)


def write_results(
    result: ExperimentResult,
    file_path: Union[str, Path],
    format: str = "auto",
) -> None:
    """
    Write experiment result to file with auto-detected format.
    
    Args:
        result: Experiment result
        file_path: Output file path
        format: Format ('json', 'csv', 'md', 'txt', 'auto')
                'auto' detects from file extension
    """
    path = Path(file_path)
    
    # Auto-detect format from extension
    if format == "auto":
        ext = path.suffix.lower()
        format_map = {
            ".json": "json",
            ".csv": "csv",
            ".md": "md",
            ".markdown": "md",
            ".txt": "txt",
        }
        format = format_map.get(ext, "txt")
    
    # Select formatter
    formatters = {
        "json": JSONFormatter,
        "csv": CSVFormatter,
        "md": MarkdownFormatter,
        "txt": ConsoleFormatter,
    }
    
    formatter_class = formatters.get(format, ConsoleFormatter)
    formatter = formatter_class()
    formatter.write(result, path)
