"""
experimenter/ast.py

AST nodes for experiment, verification, and analysis specifications.

Provides:
- ReplicationNode: Replication settings from DSL
- StatisticNode: Single statistic definition
- ExperimentOutputNode: Output settings
- ExperimentNode: Complete experiment specification
- ModelImportNode: Model import for verification
- LabelNode: Label definition for verification
- ObservableNode: Observable mapping for verification
- VerificationCheckNode: Verification check settings
- VerificationNode: Complete verification specification
- AnalysisModelNode: Model import for analysis
- AnalysisMetricsNode: Metrics settings for analysis
- AnalysisRuntimeNode: Runtime measurement settings for analysis
- AnalysisRegressionNode: Regression settings for analysis
- AnalysisOutputNode: Output settings for analysis
- AnalysisNode: Complete analysis specification
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict


# ============================================================================
# Experiment AST
# ============================================================================

@dataclass
class ReplicationNode:
    """
    Replication settings from experiment DSL.

    Attributes:
        count: Number of replications to run
        warm_up_time: Warmup period before statistics collection
        run_length: Total simulation run length
        seed_strategy: "incremental" (base_seed + rep_id) or "explicit" (use explicit_seeds)
        base_seed: Starting seed for incremental strategy
        explicit_seeds: List of seeds for explicit strategy
        generate_plots: Whether to automatically generate plots after experiment
        trace_interval: Time interval for sampling traced statistics
    """
    count: int = 30
    warm_up_time: float = 0.0
    run_length: float = 1000.0
    seed_strategy: str = "incremental"
    base_seed: int = 42
    explicit_seeds: List[int] = field(default_factory=list)
    generate_plots: bool = False
    trace_interval: float = 1.0
    
    def get_seed(self, replication_id: int) -> int:
        """
        Get seed for a specific replication.
        
        Args:
            replication_id: 0-indexed replication number
        
        Returns:
            Seed for this replication
        """
        if self.seed_strategy == "explicit" and self.explicit_seeds:
            if replication_id < len(self.explicit_seeds):
                return self.explicit_seeds[replication_id]
            # Fall back to incremental if not enough explicit seeds
            return self.base_seed + replication_id
        return self.base_seed + replication_id


@dataclass
class StatisticNode:
    """
    Single statistic definition from experiment DSL.

    Attributes:
        name: Unique identifier for this statistic
        stat_type: Type of statistic (count, time_average, utilization, duration, time_series, observation)
        expression: Expression to evaluate for the statistic
        domain: Domain name for count statistics
        condition: Filter condition
        interval: Sampling interval for time_series
        aggregation: How to aggregate values
        start_expr: Expression for duration start
        end_expr: Expression for duration end
        entity_domain: Domain of entities for duration tracking
        trace: Whether to capture time series trace for this statistic
    """
    name: str
    stat_type: str
    expression: Optional[str] = None
    domain: Optional[str] = None
    condition: Optional[str] = None
    interval: Optional[float] = None
    aggregation: str = "average"
    start_expr: Optional[str] = None
    end_expr: Optional[str] = None
    entity_domain: Optional[str] = None
    trace: bool = False


@dataclass
class ExperimentOutputNode:
    """
    Output settings from experiment DSL.
    
    Attributes:
        format: Output format (json, csv, md, txt)
        file_path: Path to output file
    """
    format: str = "json"
    file_path: str = "output/results.json"


@dataclass
class ExperimentNode:
    """
    Complete experiment specification.
    
    Attributes:
        name: Experiment name/identifier
        model_path: Path to the model .simasm file
        replication: Replication settings
        statistics: List of statistics to collect
        output: Output settings
    """
    name: str
    model_path: str
    replication: ReplicationNode
    statistics: List[StatisticNode] = field(default_factory=list)
    output: ExperimentOutputNode = field(default_factory=ExperimentOutputNode)


# ============================================================================
# Verification AST
# ============================================================================

@dataclass
class ModelImportNode:
    """
    Model import from verification DSL.
    
    Attributes:
        name: Local name for the model (used in labels/observables)
        path: Path to the .simasm model file
    """
    name: str
    path: str


@dataclass
class LabelNode:
    """
    Label definition from verification DSL.
    
    Defines an atomic proposition for a specific model.
    
    Attributes:
        name: Label name (used in observables)
        model: Model name (must match a ModelImportNode.name)
        predicate: Boolean expression to evaluate on model state
    """
    name: str
    model: str
    predicate: str


@dataclass
class ObservableNode:
    """
    Observable mapping from verification DSL.
    
    Maps labels from different models to a common observable
    for stutter equivalence checking.
    
    Attributes:
        name: Observable name
        mappings: Dict mapping model_name -> label_name
    """
    name: str
    mappings: Dict[str, str] = field(default_factory=dict)


@dataclass
class TimeseriesObservableNode:
    """
    Timeseries observable definition from verification DSL.

    Defines a numeric expression to track over time for a specific model.

    Attributes:
        name: Observable name (used to match observables across models)
        model: Model name (must match a ModelImportNode.name)
        expression: Numeric expression to evaluate on model state
    """
    name: str
    model: str
    expression: str


@dataclass
class TimeseriesPlotConfigNode:
    """
    Configuration for timeseries plot output.

    Attributes:
        layout: Tuple of (rows, cols) for subplot grid
        observable: Name of observable to plot
        y_label: Y-axis label
        y_min: Optional minimum y value
        y_max: Optional maximum y value
        show_raw: Whether to show raw traces
        show_no_stutter: Whether to show no-stutter traces
        output_file: Output filename
    """
    layout: tuple = (6, 2)
    observable: str = ""
    y_label: str = "Value"
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    show_raw: bool = True
    show_no_stutter: bool = True
    output_file: str = "timeseries_traces.png"


@dataclass
class VerificationCheckNode:
    """
    Verification check settings from DSL.

    Attributes:
        check_type: Type of check ("stutter_equivalence", "stutter_equivalence_k_induction", "trace_equivalence")
        run_length: Simulation end time for trace comparison
        timeout: Optional wall-clock timeout in seconds
        skip_init_steps: Number of steps to skip for initialization sync
        k_max: Maximum induction depth for k-induction verification (Algorithm 1)
    """
    check_type: str = "stutter_equivalence"
    run_length: float = 10.0
    timeout: Optional[float] = None
    skip_init_steps: int = 0
    k_max: Optional[int] = None


@dataclass
class VerificationOutputNode:
    """
    Output settings for verification results.

    Attributes:
        format: Output format (json, txt, md)
        file_path: Path to output file
        include_counterexample: Whether to include counterexample details
        generate_plots: Whether to generate visualization plots
    """
    format: str = "json"
    file_path: str = "output/verification_results.json"
    include_counterexample: bool = True
    generate_plots: bool = False


@dataclass
class VerificationNode:
    """
    Complete verification specification.

    Attributes:
        name: Verification name/identifier
        models: List of models to verify
        seeds: List of random seeds for multi-seed verification
        labels: List of label definitions
        observables: List of observable mappings
        timeseries_observables: List of numeric timeseries observables
        check: Verification check settings
        output: Output settings
        timeseries_plot_config: Optional configuration for timeseries plots
    """
    name: str
    models: List[ModelImportNode]
    seeds: List[int] = field(default_factory=lambda: [42])
    labels: List[LabelNode] = field(default_factory=list)
    observables: List[ObservableNode] = field(default_factory=list)
    timeseries_observables: List[TimeseriesObservableNode] = field(default_factory=list)
    check: VerificationCheckNode = field(default_factory=VerificationCheckNode)
    output: VerificationOutputNode = field(default_factory=VerificationOutputNode)
    timeseries_plot_config: Optional[TimeseriesPlotConfigNode] = None

    @property
    def seed(self) -> int:
        """Backward compatibility: return first seed."""
        return self.seeds[0] if self.seeds else 42


# ============================================================================
# Analysis AST
# ============================================================================

@dataclass
class AnalysisModelNode:
    """
    Model import from analysis DSL.

    Attributes:
        name: Local name for the model (used in results)
        path: Path to the .simasm model file
    """
    name: str
    path: str


@dataclass
class AnalysisMetricsNode:
    """
    Metrics settings from analysis DSL.

    Attributes:
        metric_type: Type of complexity analysis ("het")
        features: List of feature names to extract
    """
    metric_type: str = "het"
    features: List[str] = field(default_factory=lambda: [
        "total_het", "total_updates", "total_conditionals",
        "total_let_bindings", "total_function_calls",
        "total_new_entities", "total_list_operations",
    ])


@dataclass
class AnalysisRuntimeNode:
    """
    Runtime measurement settings from analysis DSL.

    Attributes:
        end_time: Simulation end time
        seeds: List of random seeds for measurement
        time_var: Name of simulation time variable
    """
    end_time: float = 1000.0
    seeds: List[int] = field(default_factory=lambda: [42, 123, 456])
    time_var: str = "sim_clocktime"


@dataclass
class AnalysisRegressionNode:
    """
    Regression settings from analysis DSL.

    Attributes:
        target: Target variable for regression (exec_time_sec_mean)
        predictors: List of predictor feature names
        method: Regression method (ols)
    """
    target: str = "exec_time_sec_mean"
    predictors: List[str] = field(default_factory=lambda: [
        "total_het", "total_updates",
    ])
    method: str = "ols"


@dataclass
class AnalysisOutputNode:
    """
    Output settings from analysis DSL.

    Attributes:
        format: Output format (json, csv)
        file_path: Path to output directory
        generate_plots: Whether to generate visualization plots
    """
    format: str = "json"
    file_path: str = "output/complexity_analysis/"
    generate_plots: bool = True


@dataclass
class AnalysisNode:
    """
    Complete analysis specification.

    Attributes:
        name: Analysis name/identifier
        models: List of models to analyze
        metrics: Metrics settings (what complexity features to extract)
        runtime: Runtime measurement settings
        regression: Regression settings (None to skip regression)
        output: Output settings
    """
    name: str
    models: List[AnalysisModelNode]
    metrics: AnalysisMetricsNode = field(default_factory=AnalysisMetricsNode)
    runtime: AnalysisRuntimeNode = field(default_factory=AnalysisRuntimeNode)
    regression: Optional[AnalysisRegressionNode] = None
    output: AnalysisOutputNode = field(default_factory=AnalysisOutputNode)


# ============================================================================
# Complexity Analysis AST
# ============================================================================

@dataclass
class ComplexityModelNode:
    """
    Model specification for complexity analysis.

    Attributes:
        name: Local name for the model (used in results)
        simasm_path: Path to the .simasm model file
        event_graph_path: Path to the Event Graph JSON specification
    """
    name: str
    simasm_path: str
    event_graph_path: str
    topology: str = ""


@dataclass
class ComplexityMetricsNode:
    """
    Metrics settings for complexity analysis.

    Attributes:
        het_static: Whether to compute static HET
        het_path_based: Whether to compute path-based HET
        max_cycle_traversals: Maximum cycle traversals for path enumeration
        structural: Whether to compute structural metrics (|V|, |E|, etc.)
        component_breakdown: Whether to include component breakdown
    """
    het_static: bool = True
    het_path_based: bool = True
    max_cycle_traversals: int = 1
    structural: bool = True
    component_breakdown: bool = True
    smc: bool = True
    cc: bool = True
    loc: bool = True
    kc: bool = True


@dataclass
class ComplexityOutputNode:
    """
    Output settings for complexity analysis.

    Attributes:
        format: Output format (json, csv)
        file_path: Path to output file
        generate_summary: Whether to generate summary report
        include_paths: Whether to include path breakdown in output
    """
    format: str = "json"
    file_path: str = "output/complexity_results.json"
    generate_summary: bool = True
    include_paths: bool = False


@dataclass
class ComplexityNode:
    """
    Complete complexity analysis specification.

    Attributes:
        name: Analysis name/identifier
        models: List of models to analyze (with SimASM + Event Graph paths)
        metrics: Metrics settings
        output: Output settings
    """
    name: str
    models: List[ComplexityModelNode]
    metrics: ComplexityMetricsNode = field(default_factory=ComplexityMetricsNode)
    output: ComplexityOutputNode = field(default_factory=ComplexityOutputNode)
    simasm_dir: str = ""
    json_dir: str = ""