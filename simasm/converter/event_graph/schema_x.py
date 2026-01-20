"""
Pure Event Graph JSON Schema

Defines Pydantic models for Event Graph specification WITHOUT SimASM syntax.
All SimASM code generation is handled by the translator layer.

This schema captures the semantic operations of Event Graphs:
- Vertices (events) with abstract state operations
- Scheduling edges with conditions and delays
- Cancelling edges with conditions
- State variables and random streams

Based on:
- Schruben (1983) Event Graph methodology
- Formal definition: G = (V(G), E_s(G), E_c(G), Ψ(G))
"""

from typing import Optional, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# =============================================================================
# ENUMERATIONS
# =============================================================================

class DistributionType(str, Enum):
    """Supported probability distributions for random streams."""
    EXPONENTIAL = "exponential"
    UNIFORM = "uniform"
    NORMAL = "normal"
    TRIANGULAR = "triangular"
    CONSTANT = "constant"
    EMPIRICAL = "empirical"


class VariableType(str, Enum):
    """Supported variable types."""
    NAT = "Nat"
    INT = "Int"
    REAL = "Real"
    BOOL = "Bool"
    STRING = "String"


class OperationType(str, Enum):
    """Abstract operation types for state changes."""
    INCREMENT = "increment"
    DECREMENT = "decrement"
    SET = "set"
    ADD = "add"
    SUBTRACT = "subtract"
    CREATE_ENTITY = "create_entity"
    SET_ATTRIBUTE = "set_attribute"
    ADD_TO_LIST = "add_to_list"
    REMOVE_FROM_LIST = "remove_from_list"
    INCREMENT_COUNTER = "increment_counter"
    DECREMENT_COUNTER = "decrement_counter"
    ACCUMULATE = "accumulate"
    COMPUTE = "compute"


# =============================================================================
# ABSTRACT STATE CHANGE OPERATIONS
# =============================================================================

class IncrementOp(BaseModel):
    """Increment a counter variable by 1 or specified amount."""
    op: Literal["increment"] = "increment"
    var: str = Field(description="Variable name to increment")
    amount: Union[int, str] = Field(default=1, description="Amount to increment by")


class DecrementOp(BaseModel):
    """Decrement a counter variable by 1 or specified amount."""
    op: Literal["decrement"] = "decrement"
    var: str = Field(description="Variable name to decrement")
    amount: Union[int, str] = Field(default=1, description="Amount to decrement by")


class SetOp(BaseModel):
    """Set a variable to a value."""
    op: Literal["set"] = "set"
    var: str = Field(description="Variable name")
    value: Union[str, int, float, bool] = Field(description="Value to set (can reference other variables)")


class CreateEntityOp(BaseModel):
    """Create a new entity instance and optionally store in a variable."""
    op: Literal["create_entity"] = "create_entity"
    entity_type: str = Field(description="Entity domain type (e.g., 'Load')")
    as_var: str = Field(description="Local variable name to store the new entity")


class SetAttributeOp(BaseModel):
    """Set an attribute on an entity."""
    op: Literal["set_attribute"] = "set_attribute"
    entity: str = Field(description="Entity variable name")
    attribute: str = Field(description="Attribute name")
    value: Union[str, int, float] = Field(description="Value expression")


class AddToListOp(BaseModel):
    """Add an entity to a resource list."""
    op: Literal["add_to_list"] = "add_to_list"
    list_name: str = Field(description="List name (e.g., 'arrivals', 'queues', 'serves')")
    resource: str = Field(description="Resource instance name (e.g., 'generator', 'queue', 'server')")
    entity: str = Field(description="Entity variable to add")


class RemoveFromListOp(BaseModel):
    """Remove an entity from a resource list."""
    op: Literal["remove_from_list"] = "remove_from_list"
    list_name: str = Field(description="List name")
    resource: str = Field(description="Resource instance name")
    entity: str = Field(description="Entity variable to remove")


class IncrementCounterOp(BaseModel):
    """Increment a counter owned by a resource."""
    op: Literal["increment_counter"] = "increment_counter"
    counter: str = Field(description="Counter name (e.g., 'arrival_count')")
    resource: str = Field(description="Resource instance name")
    amount: Union[int, str] = Field(default=1, description="Amount to increment by")


class DecrementCounterOp(BaseModel):
    """Decrement a counter owned by a resource."""
    op: Literal["decrement_counter"] = "decrement_counter"
    counter: str = Field(description="Counter name")
    resource: str = Field(description="Resource instance name")
    amount: Union[int, str] = Field(default=1, description="Amount to decrement by")


class AccumulateOp(BaseModel):
    """Add a value to an accumulator for statistics."""
    op: Literal["accumulate"] = "accumulate"
    accumulator: str = Field(description="Accumulator name (e.g., 'total_time_in_system')")
    resource: str = Field(description="Resource instance name")
    value: str = Field(description="Value expression to accumulate")


class ComputeOp(BaseModel):
    """Compute a value and store in a local variable."""
    op: Literal["compute"] = "compute"
    var: str = Field(description="Local variable name")
    expression: str = Field(description="Expression to compute (uses entity attributes, not SimASM syntax)")


# Union type for all state change operations
StateChangeOp = Union[
    IncrementOp,
    DecrementOp,
    SetOp,
    CreateEntityOp,
    SetAttributeOp,
    AddToListOp,
    RemoveFromListOp,
    IncrementCounterOp,
    DecrementCounterOp,
    AccumulateOp,
    ComputeOp,
]


# =============================================================================
# COMPONENT SCHEMAS
# =============================================================================

class RandomStreamSpec(BaseModel):
    """Specification for a random stream (probability distribution)."""
    distribution: DistributionType
    params: Dict[str, Union[str, float, int]] = Field(
        description="Distribution parameters. Can reference other variables by name."
    )
    stream_name: Optional[str] = Field(
        default=None,
        description="Optional name for the random stream (for reproducibility)."
    )

    class Config:
        use_enum_values = True


class StateVariableSpec(BaseModel):
    """Specification for a state variable."""
    type: VariableType
    initial: Union[int, float, bool, str]
    description: Optional[str] = None

    class Config:
        use_enum_values = True


class ParameterSpec(BaseModel):
    """Specification for a constant parameter."""
    type: VariableType
    value: Union[int, float, bool, str]
    description: Optional[str] = None

    class Config:
        use_enum_values = True


class EntitySpec(BaseModel):
    """Specification for an entity type (domain)."""
    name: str
    parent: Optional[str] = Field(default="Object")
    attributes: Dict[str, VariableType] = Field(
        default_factory=dict,
        description="Entity attributes as dynamic functions."
    )

    class Config:
        use_enum_values = True


class ResourceSpec(BaseModel):
    """Specification for a resource type (Generator, Queue, Server)."""
    type: str = Field(description="Resource domain type")
    lists: List[str] = Field(default_factory=list)
    counters: List[str] = Field(default_factory=list)
    accumulators: List[str] = Field(default_factory=list)


class PredicateSpec(BaseModel):
    """Specification for auto-generated predicates."""
    prefix: str
    observable: str = Field(description="Observable name to compare")
    values: List[int]
    ge_value: Optional[int] = None


# =============================================================================
# CONDITION SPECIFICATIONS (Abstract conditions without SimASM syntax)
# =============================================================================

class CompareCondition(BaseModel):
    """Compare a value to a threshold."""
    type: Literal["compare"] = "compare"
    left: str = Field(description="Left operand (variable, counter, list_length)")
    operator: Literal["<", "<=", "==", "!=", ">", ">="]
    right: Union[str, int, float] = Field(description="Right operand")


class ListLengthCondition(BaseModel):
    """Check length of a list."""
    type: Literal["list_length"] = "list_length"
    list_name: str
    resource: str
    operator: Literal["<", "<=", "==", "!=", ">", ">="]
    value: Union[str, int]


class AndCondition(BaseModel):
    """Logical AND of multiple conditions."""
    type: Literal["and"] = "and"
    conditions: List["ConditionSpec"]


class OrCondition(BaseModel):
    """Logical OR of multiple conditions."""
    type: Literal["or"] = "or"
    conditions: List["ConditionSpec"]


class TrueCondition(BaseModel):
    """Always true condition."""
    type: Literal["true"] = "true"


ConditionSpec = Union[CompareCondition, ListLengthCondition, AndCondition, OrCondition, TrueCondition]

# Update forward references
AndCondition.model_rebuild()
OrCondition.model_rebuild()


# =============================================================================
# PARAMETER PASSING SPECIFICATIONS
# =============================================================================

class EntityParamSpec(BaseModel):
    """Pass an entity variable as parameter."""
    type: Literal["entity"] = "entity"
    var: str = Field(description="Entity variable name")


class FirstFromListParamSpec(BaseModel):
    """Pass first entity from a list as parameter."""
    type: Literal["first_from_list"] = "first_from_list"
    list_name: str
    resource: str


ParamSpec = Union[EntityParamSpec, FirstFromListParamSpec]


# =============================================================================
# VERTEX AND EDGE SCHEMAS
# =============================================================================

class PureVertexSpec(BaseModel):
    """Event vertex with abstract state operations."""
    name: str = Field(description="Event name")
    parameters: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Event parameters as list of {name: type} dicts"
    )
    state_changes: List[StateChangeOp] = Field(
        default_factory=list,
        description="Abstract state change operations"
    )
    description: Optional[str] = None


class PureSchedulingEdgeSpec(BaseModel):
    """Scheduling edge with abstract condition."""
    source: str = Field(alias="from")
    target: str = Field(alias="to")
    delay: Union[str, int, float] = Field(default=0)
    condition: Union[ConditionSpec, Literal["true"]] = Field(default="true")
    priority: int = Field(default=0)
    parameters: List[ParamSpec] = Field(default_factory=list)
    comment: Optional[str] = None

    class Config:
        populate_by_name = True


class PureCancellingEdgeSpec(BaseModel):
    """Cancelling edge with abstract condition."""
    source: str = Field(alias="from")
    target: str = Field(alias="to")
    condition: Union[ConditionSpec, Literal["true"]] = Field(default="true")
    match_parameters: List[ParamSpec] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class PureInitialEventSpec(BaseModel):
    """Initial event specification."""
    event: str
    time: Union[str, int, float] = Field(default=0)
    parameters: List[ParamSpec] = Field(default_factory=list)
    comment: Optional[str] = None


class ObservableSpec(BaseModel):
    """Observable state for verification."""
    name: str
    return_type: str = Field(default="Nat")
    expression: str = Field(description="Expression using observable names")
    description: Optional[str] = None


class StatisticSpec(BaseModel):
    """Statistic specification."""
    name: str
    type: Literal["count", "time_average", "utilization", "duration", "observation"]
    observable: str = Field(description="Observable name to track")
    description: Optional[str] = None


# =============================================================================
# MAIN SCHEMA
# =============================================================================

class PureEventGraphSpec(BaseModel):
    """
    Complete specification for a Pure Event Graph model.

    No SimASM syntax - all code generation happens in the translator.
    """

    model_name: str
    description: Optional[str] = None

    resources: Dict[str, ResourceSpec] = Field(default_factory=dict)
    entities: Dict[str, EntitySpec] = Field(default_factory=dict)
    parameters: Dict[str, ParameterSpec] = Field(default_factory=dict)
    state_variables: Dict[str, StateVariableSpec] = Field(default_factory=dict)
    random_streams: Dict[str, RandomStreamSpec] = Field(default_factory=dict)

    vertices: List[PureVertexSpec]
    scheduling_edges: List[PureSchedulingEdgeSpec] = Field(default_factory=list)
    cancelling_edges: List[PureCancellingEdgeSpec] = Field(default_factory=list)

    initial_events: List[PureInitialEventSpec] = Field(default_factory=list)
    stopping_condition: str = Field(default="time_limit")

    observables: Dict[str, ObservableSpec] = Field(default_factory=dict)
    predicates: Dict[str, PredicateSpec] = Field(default_factory=dict)
    statistics: List[StatisticSpec] = Field(default_factory=list)

    def get_vertex(self, name: str) -> Optional[PureVertexSpec]:
        """Get a vertex by name."""
        for v in self.vertices:
            if v.name == name:
                return v
        return None

    def get_outgoing_scheduling_edges(self, vertex_name: str) -> List[PureSchedulingEdgeSpec]:
        """Get all scheduling edges from a given vertex."""
        return [e for e in self.scheduling_edges if e.source == vertex_name]

    def get_outgoing_cancelling_edges(self, vertex_name: str) -> List[PureCancellingEdgeSpec]:
        """Get all cancelling edges from a given vertex."""
        return [e for e in self.cancelling_edges if e.source == vertex_name]

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
