"""
Event Graph JSON Schema v2 - Algebraic Specification Format

This schema directly mirrors the algebraic specification from Schruben (1983):

    S = (F, C, T, Γ, G)

where:
    F = {f_v : STATES → STATES | v ∈ V(G)}     - State transition functions
    C = {c_e : STATES → {0,1} | e ∈ E(G)}      - Edge condition functions
    T = {t_e : STATES → R+ | e ∈ E_s(G)}       - Edge delay functions
    Γ = {γ_e : STATES → R | e ∈ E_s(G)}        - Priority functions
    G = (V(G), E_s(G), E_c(G), Ψ(G))           - Underlying graph

Design goals:
- JSON structure directly mirrors the algebraic formalism
- State changes use natural notation: "q := q + 1; p := p - 1"
- Conditions use predicate notation: "p > 0"
- Readable by someone familiar with Event Graph literature
- Clean, minimal syntax without verbose nested objects

References:
- Schruben (1983) original Event Graph notation
- Yücesan & Schruben (1992) formal definition
- Law (2013) Next-Event Time-Advance Algorithm
"""

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum


# =============================================================================
# ENUMERATIONS
# =============================================================================

class DistributionType(str, Enum):
    """Supported probability distributions."""
    EXPONENTIAL = "exponential"
    UNIFORM = "uniform"
    NORMAL = "normal"
    TRIANGULAR = "triangular"
    CONSTANT = "constant"


class VariableType(str, Enum):
    """Supported variable types."""
    NAT = "Nat"
    INT = "Int"
    REAL = "Real"
    BOOL = "Bool"


# =============================================================================
# VERTEX (EVENT) SPECIFICATION - State Transition Functions F
# =============================================================================

class VertexSpec(BaseModel):
    """
    Event vertex with state transition function f_v.

    The state_change field uses natural assignment notation:
        "q := q + 1"              - Single assignment
        "q := q - 1; p := p - 1"  - Multiple assignments

    Examples from formalism:
        f_Arrive: q ← q + 1
        f_StartPick: q ← q - 1; p ← p - 1
        f_EndPick: p ← p + 1
        f_EndPack: c ← c + 1
    """
    name: str = Field(description="Event name (e.g., 'Arrive', 'Start', 'Finish')")
    state_change: str = Field(
        default="",
        description="State transition function using := notation (e.g., 'q := q + 1; p := p - 1')"
    )
    description: Optional[str] = None


# =============================================================================
# SCHEDULING EDGE SPECIFICATION - Conditions C, Delays T, Priorities Γ
# =============================================================================

class SchedulingEdgeSpec(BaseModel):
    """
    Scheduling edge e = (v, w) with condition c_e, delay t_e, and priority γ_e.

    Matches the Event Graph notation:
        - Edge condition: Boolean predicate (e.g., "p > 0", "q > 0")
        - Time delay: Expression or random stream name (e.g., "T_a", "0")
        - Priority: Integer for tie-breaking

    Examples from formalism:
        Arrive → Arrive: delay=T_a, condition=true
        Arrive → StartPick: delay=0, condition=(p > 0)
        EndPick → StartPick: delay=0, condition=(q > 0)
    """
    source: str = Field(alias="from", description="Source vertex name")
    target: str = Field(alias="to", description="Target vertex name")
    delay: Union[str, int, float] = Field(
        default=0,
        description="Time delay t_e (random stream name or constant)"
    )
    condition: str = Field(
        default="true",
        description="Edge condition c_e as predicate (e.g., 'p > 0', 'true')"
    )
    priority: int = Field(
        default=0,
        description="Priority γ_e for simultaneous events (higher = first)"
    )
    description: Optional[str] = None

    class Config:
        populate_by_name = True


# =============================================================================
# CANCELLING EDGE SPECIFICATION
# =============================================================================

class CancellingEdgeSpec(BaseModel):
    """
    Cancelling edge that removes scheduled events from FEL.

    When the source event fires and condition is true, all pending
    occurrences of the target event are removed from the FEL.
    """
    source: str = Field(alias="from", description="Source vertex name")
    target: str = Field(alias="to", description="Target vertex to cancel")
    condition: str = Field(
        default="true",
        description="Condition for cancellation"
    )

    class Config:
        populate_by_name = True


# =============================================================================
# INITIAL EVENT SPECIFICATION - FEL_0
# =============================================================================

class InitialEventSpec(BaseModel):
    """
    Initial event scheduled at simulation start.

    Specifies FEL_0 = {(event, time), ...}
    """
    event: str = Field(description="Event vertex name")
    time: Union[str, int, float] = Field(
        default=0,
        description="Scheduled time (constant or random stream)"
    )


# =============================================================================
# SUPPORTING SPECIFICATIONS
# =============================================================================

class StateVariableSpec(BaseModel):
    """
    State variable specification.

    Corresponds to the STATES space in the formalism.
    """
    type: str = Field(default="Nat", description="Variable type (Nat, Int, Real, Bool)")
    initial: Union[int, float, bool, str] = Field(description="Initial value")
    description: Optional[str] = None


class ParameterSpec(BaseModel):
    """Constant parameter specification."""
    type: str = Field(default="Nat")
    value: Union[int, float, bool, str]
    description: Optional[str] = None


class RandomStreamSpec(BaseModel):
    """
    Random stream specification for stochastic delays.

    Corresponds to t_e functions that draw from distributions.
    """
    distribution: str = Field(description="Distribution type (exponential, uniform, etc.)")
    params: Dict[str, Union[str, float, int]] = Field(
        description="Distribution parameters (can reference other variables)"
    )
    stream_name: Optional[str] = None


class ObservableSpec(BaseModel):
    """Observable state for output/verification."""
    expression: str = Field(description="Expression using state variables")
    return_type: str = Field(default="Nat")
    description: Optional[str] = None


class StatisticSpec(BaseModel):
    """Statistic collection specification."""
    name: str
    type: str = Field(description="Statistic type (time_average, count, etc.)")
    observable: str = Field(description="Observable name to track")
    description: Optional[str] = None


# =============================================================================
# MAIN SCHEMA - Event Graph Model S = (F, C, T, Γ, G)
# =============================================================================

class EventGraphSpec(BaseModel):
    """
    Complete Event Graph specification using algebraic format.

    This schema maps directly to the formal definition:
        S = (F, C, T, Γ, G)

    Structure:
        - vertices: V(G) with state transition functions F
        - scheduling_edges: E_s(G) with C, T, Γ
        - cancelling_edges: E_c(G)
        - state_variables: STATES space
        - initial_events: FEL_0
    """

    model_name: str
    description: Optional[str] = None

    # State space definition
    state_variables: Dict[str, StateVariableSpec] = Field(
        default_factory=dict,
        description="STATES space - the state variables tracked by the model"
    )
    parameters: Dict[str, ParameterSpec] = Field(
        default_factory=dict,
        description="Constant parameters"
    )
    random_streams: Dict[str, RandomStreamSpec] = Field(
        default_factory=dict,
        description="Random streams for stochastic delays (t_e functions)"
    )

    # Graph structure G = (V, E_s, E_c)
    vertices: List[VertexSpec] = Field(
        description="V(G) - Event vertices with state transition functions F"
    )
    scheduling_edges: List[SchedulingEdgeSpec] = Field(
        default_factory=list,
        description="E_s(G) - Scheduling edges with conditions C, delays T, priorities Γ"
    )
    cancelling_edges: List[CancellingEdgeSpec] = Field(
        default_factory=list,
        description="E_c(G) - Cancelling edges"
    )

    # Initial conditions
    initial_events: List[InitialEventSpec] = Field(
        default_factory=list,
        description="FEL_0 - Initial event list"
    )

    # Simulation control
    stopping_condition: str = Field(
        default="sim_clocktime >= sim_end_time",
        description="Termination condition"
    )

    # Output specification
    observables: Dict[str, ObservableSpec] = Field(
        default_factory=dict,
        description="Observable state functions for output"
    )
    statistics: List[StatisticSpec] = Field(
        default_factory=list,
        description="Statistics to collect"
    )

    def get_vertex(self, name: str) -> Optional[VertexSpec]:
        """Get a vertex by name."""
        for v in self.vertices:
            if v.name == name:
                return v
        return None

    def get_outgoing_edges(self, vertex_name: str) -> List[SchedulingEdgeSpec]:
        """Get all scheduling edges from a given vertex."""
        return [e for e in self.scheduling_edges if e.source == vertex_name]

    def validate_graph(self) -> List[str]:
        """Validate the Event Graph structure."""
        errors = []
        vertex_names = {v.name for v in self.vertices}

        for edge in self.scheduling_edges:
            if edge.source not in vertex_names:
                errors.append(f"Scheduling edge from unknown vertex: {edge.source}")
            if edge.target not in vertex_names:
                errors.append(f"Scheduling edge to unknown vertex: {edge.target}")

        for edge in self.cancelling_edges:
            if edge.source not in vertex_names:
                errors.append(f"Cancelling edge from unknown vertex: {edge.source}")
            if edge.target not in vertex_names:
                errors.append(f"Cancelling edge to unknown vertex: {edge.target}")

        for ie in self.initial_events:
            if ie.event not in vertex_names:
                errors.append(f"Initial event references unknown vertex: {ie.event}")

        return errors

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventGraphSpec":
        """Create an EventGraphSpec from a dictionary (JSON-compatible)."""
        return parse_eg_json(data)


# =============================================================================
# JSON LOADING
# =============================================================================

def load_eg_from_json(json_path: str) -> EventGraphSpec:
    """Load an Event Graph v2 specification from a JSON file."""
    import json
    with open(json_path, 'r') as f:
        data = json.load(f)
    return parse_eg_json(data)


def parse_eg_json(data: Dict[str, Any]) -> EventGraphSpec:
    """Parse Event Graph JSON data into an EventGraphSpec."""

    # Parse state variables
    state_variables = {}
    for name, sv in data.get("state_variables", {}).items():
        state_variables[name] = StateVariableSpec(**sv)

    # Parse parameters
    parameters = {}
    for name, p in data.get("parameters", {}).items():
        parameters[name] = ParameterSpec(**p)

    # Parse random streams
    random_streams = {}
    for name, rs in data.get("random_streams", {}).items():
        random_streams[name] = RandomStreamSpec(**rs)

    # Parse vertices
    vertices = []
    for v in data.get("vertices", []):
        vertices.append(VertexSpec(**v))

    # Parse scheduling edges
    scheduling_edges = []
    for e in data.get("scheduling_edges", []):
        scheduling_edges.append(SchedulingEdgeSpec(**e))

    # Parse cancelling edges
    cancelling_edges = []
    for e in data.get("cancelling_edges", []):
        cancelling_edges.append(CancellingEdgeSpec(**e))

    # Parse initial events
    initial_events = []
    for ie in data.get("initial_events", []):
        initial_events.append(InitialEventSpec(**ie))

    # Parse observables
    observables = {}
    for name, obs in data.get("observables", {}).items():
        observables[name] = ObservableSpec(**obs)

    # Parse statistics
    statistics = []
    for stat in data.get("statistics", []):
        statistics.append(StatisticSpec(**stat))

    return EventGraphSpec(
        model_name=data["model_name"],
        description=data.get("description"),
        state_variables=state_variables,
        parameters=parameters,
        random_streams=random_streams,
        vertices=vertices,
        scheduling_edges=scheduling_edges,
        cancelling_edges=cancelling_edges,
        initial_events=initial_events,
        stopping_condition=data.get("stopping_condition", "sim_clocktime >= sim_end_time"),
        observables=observables,
        statistics=statistics
    )
