"""
experimenter/ast.py

AST nodes for experiment and verification specifications.

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
        check: Verification check settings
        output: Output settings
    """
    name: str
    models: List[ModelImportNode]
    seeds: List[int] = field(default_factory=lambda: [42])
    labels: List[LabelNode] = field(default_factory=list)
    observables: List[ObservableNode] = field(default_factory=list)
    check: VerificationCheckNode = field(default_factory=VerificationCheckNode)
    output: VerificationOutputNode = field(default_factory=VerificationOutputNode)

    @property
    def seed(self) -> int:
        """Backward compatibility: return first seed."""
        return self.seeds[0] if self.seeds else 42