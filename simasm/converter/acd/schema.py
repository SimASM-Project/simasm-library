"""
Activity Cycle Diagram JSON Schema v2 - Activity Transition Table Format

This schema mirrors the Activity Transition Table from the ACD formalism:

| Activity | At-begin          | BTO-event    | At-end                              |
|----------|-------------------|--------------|-------------------------------------|
|          | Condition | Action| Time | Name | Arc | Condition | Action | Influences |

Based on:
- Tocher (1960) original ACD notation
- Carrie (1988) formal definition
- Activity Transition Table from ByongKyu (2013)

Design goals:
- JSON structure directly mirrors the Activity Transition Table
- Readable by someone familiar with ACD literature
- Clean, minimal syntax without verbose nested objects
"""

from typing import Optional, List, Dict, Any, Union, Literal
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
    STRING = "String"


# =============================================================================
# ACTIVITY TRANSITION TABLE COMPONENTS
# =============================================================================

class AtBeginSpec(BaseModel):
    """
    At-begin part of Activity Transition Table.

    Specifies when an activity may start and what happens immediately.

    Example from table:
        Condition: (M1 > 0) & (Q1 >= m1)
        Action: M1--; Q1 = Q1 - m1;
    """
    condition: str = Field(
        description="Enabling predicate (e.g., 'marking(C) >= 1')"
    )
    action: str = Field(
        default="",
        description="State changes at begin (e.g., 'C--' or 'S--; Q--')"
    )
    bind: List[str] = Field(
        default_factory=list,
        description="Token bindings (e.g., ['creator:C', 'job:Q'])"
    )
    set: List[str] = Field(
        default_factory=list,
        description="Attribute assignments (e.g., ['job.service_start_time = sim_clocktime'])"
    )


class BTOEventSpec(BaseModel):
    """
    BTO-event (Bound-to-Occur) part of Activity Transition Table.

    Represents the guaranteed completion of an activity.

    Example from table:
        Time: tp
        Name: Processed1
    """
    time: str = Field(
        description="Duration expression (random stream name or expression)"
    )
    name: str = Field(
        description="Event name for completion (e.g., 'Created', 'Served')"
    )


class AtEndArcSpec(BaseModel):
    """
    Single arc in At-end part of Activity Transition Table.

    Activities can have multiple output arcs with conditions.

    Example from table:
        Arc: 1
        Condition: TRUE
        Action: M1++;
        Influences: Process1
    """
    arc: int = Field(
        default=1,
        description="Arc index (1, 2, 3...)"
    )
    condition: str = Field(
        default="true",
        description="Arc condition (e.g., 'true' or 'c1 == 1')"
    )
    action: str = Field(
        description="State changes (e.g., 'C++' or 'S++; Jobs++ <- job')"
    )
    influences: List[str] = Field(
        default_factory=list,
        description="Activities that may become enabled"
    )
    # For statistics collection at end
    compute: List[str] = Field(
        default_factory=list,
        description="Local computations (e.g., ['time_in_system = sim_clocktime - job.arrival_time'])"
    )
    accumulate: List[str] = Field(
        default_factory=list,
        description="Accumulator updates (e.g., ['total_sojourn_time += time_in_system'])"
    )


class ActivitySpec(BaseModel):
    """
    Activity definition matching Activity Transition Table format.

    Each row in the table becomes one ActivitySpec.
    """
    name: str = Field(description="Activity name")
    priority: int = Field(
        default=1,
        description="Scanning priority (lower = scanned first)"
    )
    at_begin: AtBeginSpec = Field(
        description="At-begin specification"
    )
    bto_event: BTOEventSpec = Field(
        description="BTO-event specification"
    )
    at_end: List[AtEndArcSpec] = Field(
        description="At-end arcs"
    )
    description: Optional[str] = None


# =============================================================================
# SUPPORTING COMPONENTS
# =============================================================================

class QueueSpec(BaseModel):
    """Queue (passive state) specification."""
    initial_marking: Union[int, str] = Field(
        default=0,
        description="Initial token count (μ₀)"
    )
    token_type: str = Field(
        default="Token",
        description="Type of tokens (Job, Resource, etc.)"
    )
    is_resource: bool = Field(
        default=False,
        description="True if queue holds reusable resources"
    )
    description: Optional[str] = None


class TokenTypeSpec(BaseModel):
    """Token type definition."""
    name: str
    parent: str = Field(default="Token")
    attributes: Dict[str, str] = Field(
        default_factory=dict,
        description="Attribute name -> type mapping"
    )
    description: Optional[str] = None


class ParameterSpec(BaseModel):
    """Constant parameter specification."""
    type: str
    value: Union[int, float, bool, str]
    description: Optional[str] = None


class RandomStreamSpec(BaseModel):
    """Random stream specification."""
    distribution: str
    params: Dict[str, Union[str, float, int]]
    stream_name: Optional[str] = None


class ObservableSpec(BaseModel):
    """Observable state specification."""
    name: str
    return_type: str = Field(default="Nat")
    expression: str
    description: Optional[str] = None


class StatisticSpec(BaseModel):
    """Statistic collection specification."""
    name: str
    type: str
    observable: str
    description: Optional[str] = None


class StateVariableSpec(BaseModel):
    """State variable specification."""
    type: str
    initial: Union[int, float, str]


# =============================================================================
# MAIN SCHEMA
# =============================================================================

class ACDSpec(BaseModel):
    """
    Complete ACD specification using Activity Transition Table format.

    This schema is designed to be:
    1. Readable by someone familiar with ACD formalism
    2. Direct mapping from Activity Transition Table
    3. Clean JSON without verbose nested structures
    """

    model_name: str
    description: Optional[str] = None

    # Model components
    parameters: Dict[str, ParameterSpec] = Field(default_factory=dict)
    token_types: Dict[str, TokenTypeSpec] = Field(default_factory=dict)
    queues: Dict[str, QueueSpec]
    activities: List[ActivitySpec]
    random_streams: Dict[str, RandomStreamSpec] = Field(default_factory=dict)
    state_variables: Dict[str, StateVariableSpec] = Field(default_factory=dict)

    # Simulation control
    stopping_condition: str = Field(default="sim_clocktime >= sim_end_time")

    # Observables and statistics
    observables: Dict[str, ObservableSpec] = Field(default_factory=dict)
    statistics: List[StatisticSpec] = Field(default_factory=list)

    # Fine-grained semantics configuration (optional)
    fine_grained_semantics: Optional[Dict[str, Any]] = None

    def get_activities_by_priority(self) -> List[ActivitySpec]:
        """Get activities sorted by priority (for scanning order)."""
        return sorted(self.activities, key=lambda a: a.priority)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACDSpec":
        """Create an ACDSpec from a dictionary (JSON-compatible)."""
        return parse_acd_json(data)


# =============================================================================
# JSON LOADING
# =============================================================================

def load_acd_from_json(json_path: str) -> ACDSpec:
    """Load an ACD v2 specification from a JSON file."""
    import json
    with open(json_path, 'r') as f:
        data = json.load(f)
    return parse_acd_json(data)


def parse_acd_json(data: Dict[str, Any]) -> ACDSpec:
    """Parse ACD JSON data into an ACDSpec."""

    # Parse parameters
    parameters = {}
    for name, p in data.get("parameters", {}).items():
        parameters[name] = ParameterSpec(**p)

    # Parse token types
    token_types = {}
    for name, tt in data.get("token_types", {}).items():
        # Handle simple attribute format: {"attr": "Type"}
        attrs = tt.get("attributes", {})
        if attrs:
            simple_attrs = {}
            for attr_name, attr_val in attrs.items():
                if isinstance(attr_val, dict):
                    simple_attrs[attr_name] = attr_val.get("type", "Real")
                else:
                    simple_attrs[attr_name] = attr_val
            tt["attributes"] = simple_attrs
        token_types[name] = TokenTypeSpec(name=name, **{k: v for k, v in tt.items() if k != "name"})

    # Parse queues
    queues = {}
    for name, q in data.get("queues", {}).items():
        queues[name] = QueueSpec(**q)

    # Parse activities
    activities = []
    for act in data.get("activities", []):
        at_begin = AtBeginSpec(**act["at_begin"])
        bto_event = BTOEventSpec(**act["bto_event"])
        at_end = [AtEndArcSpec(**arc) for arc in act["at_end"]]

        activities.append(ActivitySpec(
            name=act["name"],
            priority=act.get("priority", 1),
            at_begin=at_begin,
            bto_event=bto_event,
            at_end=at_end,
            description=act.get("description")
        ))

    # Parse random streams
    random_streams = {}
    for name, rs in data.get("random_streams", {}).items():
        random_streams[name] = RandomStreamSpec(**rs)

    # Parse state variables
    state_variables = {}
    for name, sv in data.get("state_variables", {}).items():
        if isinstance(sv, dict):
            state_variables[name] = StateVariableSpec(**sv)
        else:
            state_variables[name] = StateVariableSpec(type="Nat", initial=sv)

    # Parse observables
    observables = {}
    for name, obs in data.get("observables", {}).items():
        observables[name] = ObservableSpec(name=name, **{k: v for k, v in obs.items() if k != "name"})

    # Parse statistics
    statistics = []
    for stat in data.get("statistics", []):
        statistics.append(StatisticSpec(**stat))

    return ACDSpec(
        model_name=data["model_name"],
        description=data.get("description"),
        parameters=parameters,
        token_types=token_types,
        queues=queues,
        activities=activities,
        random_streams=random_streams,
        state_variables=state_variables,
        stopping_condition=data.get("stopping_condition", "sim_clocktime >= sim_end_time"),
        observables=observables,
        statistics=statistics,
        fine_grained_semantics=data.get("fine_grained_semantics")
    )
