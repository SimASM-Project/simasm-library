"""
Data models for the SMC profiler.

Profiler-specific models only. The profiler reuses SchedulingSubgraph,
SchedulingEdge, and CycleInfo from smc_complexity.models.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..models import SchedulingSubgraph, CycleInfo, SMCResult


@dataclass
class StreamInfo:
    var_name: str
    distribution: str
    param_exprs: Tuple[str, ...]
    param_values: Tuple[float, ...]
    stream_name: Optional[str]
    mean_delay: float


@dataclass
class RCGNode:
    rule_name: str
    het_cost: int
    is_init: bool
    is_recurring: bool
    is_control: bool
    streams: List[str] = field(default_factory=list)


@dataclass
class RCGEdge:
    from_rule: str
    to_rule: str
    guard: Optional[str] = None
    is_dispatch: bool = False


@dataclass
class RuleCallGraph:
    nodes: Dict[str, RCGNode] = field(default_factory=dict)
    edges: List[RCGEdge] = field(default_factory=list)
    adjacency: Dict[str, List[RCGEdge]] = field(default_factory=dict)


@dataclass
class ProfilerResult:
    model_name: str
    streams: Dict[str, StreamInfo]
    rcg: RuleCallGraph
    scheduling_subgraph: SchedulingSubgraph
    cycles: List[CycleInfo]
    num_cycles: int
    scr: float
    smc: float
    t_sim: float
    event_het: Dict[str, int]
    c_step: int
    c_init: int
    smc_original: int
    smc_fan_weighted: int
    smc_degree_weighted: int
    smc_rate_structural: float
    smc_per_vertex_rate: float
    smc_v11: float
    vertex_count: int
    edge_count: int
    computation_time_ms: float

    def to_smc_result(self) -> SMCResult:
        return SMCResult(
            model_name=self.model_name,
            event_het=self.event_het,
            c_step=self.c_step,
            c_init=self.c_init,
            cycles=self.cycles,
            num_cycles=self.num_cycles,
            scr=self.scr,
            smc=self.smc,
            t_sim=self.t_sim,
            smc_original=self.smc_original,
            smc_fan_weighted=self.smc_fan_weighted,
            smc_degree_weighted=self.smc_degree_weighted,
            smc_rate_structural=self.smc_rate_structural,
            smc_per_vertex_rate=self.smc_per_vertex_rate,
            smc_v11=self.smc_v11,
            computation_time_ms=self.computation_time_ms,
            vertex_count=self.vertex_count,
            edge_count=self.edge_count,
        )

    def to_dot(self, title: str = "") -> str:
        from .graph_export import export_dot
        if not title:
            title = self.model_name
        return export_dot(self.rcg, self.scheduling_subgraph, self.cycles, self.streams, title)

    def to_mermaid(self) -> str:
        from .graph_export import export_mermaid
        return export_mermaid(self.rcg, self.scheduling_subgraph, self.cycles, self.streams)

    def to_graph_json(self) -> dict:
        from .graph_export import export_graph_json
        return export_graph_json(self.rcg, self.scheduling_subgraph, self.cycles, self.streams)
