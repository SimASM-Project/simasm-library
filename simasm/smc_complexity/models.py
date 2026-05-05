"""
Data classes for SMC v10 complexity analysis.

SMC(G) = C_ctrl + Sigma_v rate(v) * deg*(v) * C(P_E,v)

Where:
- C_ctrl = 89 (fixed control overhead: C_STEP + C_PINIT)
- rate(v) = min(rate_raw(v), lambda_max) -- firing rate with source-rate cap
- deg*(v) = max(1, d_in(v) + d_out(v)) -- scheduling subgraph degree
- C(P_E,v) = HET cost of event rule at vertex v
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


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
class VertexDetail:
    """Per-vertex breakdown for SMC v10."""
    name: str
    het_cost: int
    rate: float
    degree: int
    contribution: float


@dataclass
class SMCResult:
    """Complete SMC v10 analysis result."""
    model_name: str
    smc: float
    control_overhead: int
    vertex_details: List[VertexDetail]
    # Additional diagnostics
    event_het: Dict[str, int] = field(default_factory=dict)
    cycles: List[CycleInfo] = field(default_factory=list)
    num_cycles: int = 0
    source_rate: float = 0.0
    vertex_count: int = 0
    edge_count: int = 0
    computation_time_ms: float = 0.0
