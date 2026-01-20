"""
simulation - Statistics collection and experiment management.

Provides:
- ExperimentConfig: Complete experiment configuration
- ReplicationSettings: Settings for replications
- StatisticConfig: Configuration for individual statistics
- StatisticType: Enum of statistic types
- AggregationType: Enum of aggregation methods
- Statistic classes: CountStatistic, TimeAverageStatistic, etc.
- StatisticResult: Holds computed statistic results
- StatisticsCollector: Collects statistics during simulation
- ExperimentRunner: Runs replications and aggregates results
- Output formatters: JSON, CSV, Console, Markdown
- Plotting: Automatic visualization with PlotConfig and generate_experiment_plots
"""

from simasm.simulation.config import (
    StatisticType,
    AggregationType,
    StatisticConfig,
    ReplicationSettings,
    ExperimentConfig,
    ConfigError,
)

from simasm.simulation.statistics import (
    StatisticResult,
    Statistic,
    CountStatistic,
    TimeAverageStatistic,
    UtilizationStatistic,
    DurationStatistic,
    TimeSeriesStatistic,
    ObservationStatistic,
    create_statistic,
)

from simasm.simulation.collector import (
    ExpressionParser,
    get_expression_parser,
    parse_expression,
    StatisticsCollector,
)

from simasm.simulation.runner import (
    ReplicationResult,
    SummaryStatistics,
    ExperimentResult,
    ExperimentRunner,
    SimpleModelRunner,
    run_replications,
)

from simasm.simulation.output import (
    OutputConfig,
    OutputFormatter,
    JSONFormatter,
    CSVFormatter,
    ConsoleFormatter,
    MarkdownFormatter,
    to_json,
    to_csv,
    to_console,
    to_markdown,
    write_results,
)

from simasm.simulation.plotting import (
    PlotConfig,
    generate_experiment_plots,
)

__all__ = [
    # Config
    "StatisticType",
    "AggregationType",
    "StatisticConfig",
    "ReplicationSettings",
    "ExperimentConfig",
    "ConfigError",
    # Statistics
    "StatisticResult",
    "Statistic",
    "CountStatistic",
    "TimeAverageStatistic",
    "UtilizationStatistic",
    "DurationStatistic",
    "TimeSeriesStatistic",
    "ObservationStatistic",
    "create_statistic",
    # Collector
    "ExpressionParser",
    "get_expression_parser",
    "parse_expression",
    "StatisticsCollector",
    # Runner
    "ReplicationResult",
    "SummaryStatistics",
    "ExperimentResult",
    "ExperimentRunner",
    "SimpleModelRunner",
    "run_replications",
    # Output
    "OutputConfig",
    "OutputFormatter",
    "JSONFormatter",
    "CSVFormatter",
    "ConsoleFormatter",
    "MarkdownFormatter",
    "to_json",
    "to_csv",
    "to_console",
    "to_markdown",
    "write_results",
    # Plotting
    "PlotConfig",
    "generate_experiment_plots",
]
