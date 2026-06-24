"""
Data classes for SMC cycle-rate complexity analysis.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union


@dataclass
class SchedulingEdge:
    """A scheduling edge in the Event Graph."""
    from_vertex: str
    to_vertex: str
    delay_expr: str
    condition: str = "true"
    priority: int = 0
    mean_delay: float = 0.0


@dataclass
class SchedulingSubgraph:
    """Scheduling subgraph extracted from EG JSON."""
    vertices: List[str]
    edges: List[SchedulingEdge]
    adjacency: Dict[str, List[SchedulingEdge]]
    random_streams: Dict[str, dict]
    parameters: Dict[str, float]
    t_sim: float
    source_vertex: Optional[str] = None


@dataclass
class CycleInfo:
    """A fundamental cycle found by DFS."""
    index: int
    vertices: List[str]
    edges: List[SchedulingEdge]
    cost: int
    period: float
    rate: float


@dataclass
class SMCResult:
    """Complete SMC analysis result."""
    model_name: str
    event_het: Dict[str, int]
    c_step: int
    c_init: int
    cycles: List[CycleInfo]
    num_cycles: int
    scr: float
    smc: float
    t_sim: float
    smc_original: int
    smc_fan_weighted: int = 0
    smc_degree_weighted: int = 0
    smc_rate_structural: float = 0.0
    smc_per_vertex_rate: float = 0.0
    smc_v11: float = 0.0
    computation_time_ms: float = 0.0
    vertex_count: int = 0
    edge_count: int = 0
