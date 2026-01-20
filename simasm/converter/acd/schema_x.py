"""
Activity Cycle Diagram JSON Schema

Defines the Pydantic models for Activity Cycle Diagram specification based on:
- Tocher (1960) original ACD notation
- Carrie (1988) formal definition
- Extended ACD with arc conditions and multiplicities
- Formal definition: N = ⟨A, Q, I, O, W⁻, W⁺, G, T, μ₀⟩

The schema captures:
- Queues (passive states) with initial token counts
- Activities (active states) with durations
- At-begin conditions and actions (token consumption)
- At-end conditions and actions (token production)
- Activity priorities for deterministic scanning order

Fine-grained step semantics:
- One ASM step = start ONE activity OR execute ONE BTO event
- Enables trace equivalence with Event Graph models
"""

from typing import Optional, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


# =============================================================================
# ENUMERATIONS
# =============================================================================

class DistributionType(str, Enum):
    """Supported probability distributions for activity durations."""
    EXPONENTIAL = "exponential"
    UNIFORM = "uniform"
    NORMAL = "normal"
    TRIANGULAR = "triangular"
    CONSTANT = "constant"
    EMPIRICAL = "empirical"


class VariableType(str, Enum):
    """Supported variable types in SimASM."""
    NAT = "Nat"
    INT = "Int"
    REAL = "Real"
    BOOL = "Bool"
    STRING = "String"


class TokenType(str, Enum):
    """Base token types."""
    RESOURCE = "Resource"
    ENTITY = "Entity"
    JOB = "Job"
    CUSTOM = "Custom"


# =============================================================================
# COMPONENT SCHEMAS
# =============================================================================

class RandomStreamSpec(BaseModel):
    """
    Specification for a random stream (probability distribution).

    Maps to SimASM: var name: rnd.distribution(params) as "stream_name"
    """
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


class ParameterSpec(BaseModel):
    """
    Specification for a constant parameter.

    Maps to SimASM: const name: Type (with value set in init block)
    """
    type: VariableType
    value: Union[int, float, bool, str]
    description: Optional[str] = None

    class Config:
        use_enum_values = True


class TokenAttributeSpec(BaseModel):
    """
    Specification for a token attribute (tracked per-token state).

    Maps to SimASM: dynamic function attr(t: TokenType): AttrType
    """
    type: VariableType
    description: Optional[str] = None

    class Config:
        use_enum_values = True


class QueueSpec(BaseModel):
    """
    Specification for a queue (passive state in ACD).

    Corresponds to Q in the formal definition.
    Queues hold tokens and are represented as ovals in the diagram.

    Maps to SimASM:
    - const queue_name: Queue
    - dynamic function marking(q: Queue): Nat
    - dynamic function tokens(q: Queue): List<TokenType>
    """
    initial_tokens: int = Field(
        default=0,
        ge=0,
        description="Initial number of tokens (μ₀)"
    )
    token_type: str = Field(
        default="Token",
        description="Type of tokens this queue holds"
    )
    description: Optional[str] = None

    # For resource queues that hold reusable resources
    is_resource: bool = Field(
        default=False,
        description="If true, tokens are resources (reusable)"
    )


class TokenConsumeSpec(BaseModel):
    """
    Specification for token consumption at activity begin.

    Corresponds to W⁻(a, q) in the formal definition.
    """
    queue: str = Field(description="Queue name to consume from")
    count: int = Field(
        default=1,
        ge=1,
        description="Number of tokens to consume (arc multiplicity)"
    )
    bind_as: Optional[str] = Field(
        default=None,
        description="Variable name to bind consumed token(s) for use in at-end"
    )


class TokenProduceSpec(BaseModel):
    """
    Specification for token production at activity end.

    Corresponds to W⁺(a, q) in the formal definition.
    """
    queue: str = Field(description="Queue name to produce to")
    count: int = Field(
        default=1,
        ge=1,
        description="Number of tokens to produce (arc multiplicity)"
    )
    token_source: Optional[str] = Field(
        default=None,
        description="Bound token variable to release, or 'new' for new token"
    )
    condition: str = Field(
        default="true",
        description="Arc condition (for conditional routing)"
    )


class AtBeginSpec(BaseModel):
    """
    Specification for activity at-begin (instantiation).

    When an activity begins:
    1. Check enabling condition (all input queues have enough tokens + guard)
    2. Consume tokens from input queues
    3. Schedule BTO event for activity completion
    """
    condition: str = Field(
        default="true",
        description="Additional guard condition beyond token availability"
    )
    consume: List[TokenConsumeSpec] = Field(
        default_factory=list,
        description="Tokens to consume from input queues"
    )
    actions: List[str] = Field(
        default_factory=list,
        description="Additional state updates at activity begin"
    )


class AtEndArcSpec(BaseModel):
    """
    Specification for one output arc at activity end.

    Activities can have multiple output arcs with conditions
    for routing tokens to different queues.
    """
    condition: str = Field(
        default="true",
        description="Arc condition (must be true for this arc to fire)"
    )
    produce: List[TokenProduceSpec] = Field(
        default_factory=list,
        description="Tokens to produce to output queues"
    )
    actions: List[str] = Field(
        default_factory=list,
        description="Additional state updates for this arc"
    )


class ActivitySpec(BaseModel):
    """
    Specification for an activity (active state in ACD).

    Corresponds to A in the formal definition.
    Activities are represented as rectangles in the diagram.

    Each activity has:
    - Duration T(a)
    - At-begin specification (condition + consume)
    - At-end specification (produce + conditions)
    - Priority for scanning order (fine-grained semantics)
    """
    name: str = Field(description="Activity name")
    duration: Union[str, int, float] = Field(
        description="Duration expression (random stream name, variable, or literal)"
    )
    priority: int = Field(
        default=0,
        description="Scanning priority (lower = scanned first, for determinism)"
    )
    at_begin: AtBeginSpec = Field(
        default_factory=AtBeginSpec,
        description="At-begin specification"
    )
    at_end: List[AtEndArcSpec] = Field(
        default_factory=list,
        description="At-end output arcs"
    )
    description: Optional[str] = None

    @model_validator(mode='after')
    def validate_at_end_default(self):
        """Ensure at_end has at least one arc if not specified."""
        if not self.at_end:
            # Default: single unconditional arc with no production
            # (activity produces no tokens - unusual but valid)
            pass
        return self


class TokenTypeSpec(BaseModel):
    """
    Specification for a token type (entity flowing through the diagram).

    Maps to SimASM domain declaration.
    """
    name: str
    parent: str = Field(
        default="Token",
        description="Parent domain"
    )
    attributes: Dict[str, TokenAttributeSpec] = Field(
        default_factory=dict,
        description="Token attributes (per-entity state)"
    )
    description: Optional[str] = None


class ObservableSpec(BaseModel):
    """
    Specification for observable state (derived functions).

    Used for verification and statistics collection.
    """
    name: str
    expression: str = Field(description="SimASM expression for the observable")
    description: Optional[str] = None


class StatisticSpec(BaseModel):
    """
    Specification for a statistic to collect during simulation.
    """
    name: str
    type: Literal["count", "time_average", "utilization", "duration", "observation"]
    expression: str
    description: Optional[str] = None
    # For duration statistics
    start_expr: Optional[str] = None
    end_expr: Optional[str] = None
    entity_domain: Optional[str] = None


# =============================================================================
# MAIN SCHEMA
# =============================================================================

class ACDSpec(BaseModel):
    """
    Complete specification for an Activity Cycle Diagram model.

    Corresponds to the formal definition:
    N = ⟨A, Q, I, O, W⁻, W⁺, G, T, μ₀⟩

    This schema captures all components needed to generate SimASM code
    that implements the ACD using fine-grained Activity Scanning Algorithm.

    Fine-grained step semantics (for trace equivalence):
    - Phase-based state machine: init → scan → time → execute → scan → ...
    - Scanning phase starts AT MOST ONE activity per step
    - Activities are scanned in priority order (lower priority value = first)
    - This ensures deterministic behavior and trace equivalence with Event Graph
    """

    # Model metadata
    model_name: str = Field(description="Name of the model (becomes SimASM filename)")
    description: Optional[str] = Field(
        default=None,
        description="Model description (becomes header comment)"
    )

    # Parameters (constants)
    parameters: Dict[str, ParameterSpec] = Field(
        default_factory=dict,
        description="Model parameters (SimASM constants)"
    )

    # Token types
    token_types: Dict[str, TokenTypeSpec] = Field(
        default_factory=dict,
        description="Token type definitions (SimASM domains)"
    )

    # Queues (passive states)
    queues: Dict[str, QueueSpec] = Field(
        description="Queue definitions Q"
    )

    # Activities (active states)
    activities: List[ActivitySpec] = Field(
        description="Activity definitions A"
    )

    # Random streams for durations
    random_streams: Dict[str, RandomStreamSpec] = Field(
        default_factory=dict,
        description="Random number streams for stochastic durations"
    )

    # Additional state variables (beyond marking)
    state_variables: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional state variables"
    )

    # Termination
    stopping_condition: str = Field(
        default="sim_clocktime >= sim_end_time",
        description="Condition to stop simulation"
    )

    # Observables (for verification)
    observables: Dict[str, ObservableSpec] = Field(
        default_factory=dict,
        description="Observable state for verification and statistics"
    )

    # Statistics configuration
    statistics: List[StatisticSpec] = Field(
        default_factory=list,
        description="Statistics to collect during simulation"
    )

    def get_activity(self, name: str) -> Optional[ActivitySpec]:
        """Get an activity by name."""
        for a in self.activities:
            if a.name == name:
                return a
        return None

    def get_activities_by_priority(self) -> List[ActivitySpec]:
        """Get activities sorted by priority (for scanning order)."""
        return sorted(self.activities, key=lambda a: a.priority)

    def get_input_queues(self, activity_name: str) -> List[str]:
        """Get input queues for an activity (I(a))."""
        activity = self.get_activity(activity_name)
        if activity:
            return [c.queue for c in activity.at_begin.consume]
        return []

    def get_output_queues(self, activity_name: str) -> List[str]:
        """Get output queues for an activity (O(a))."""
        activity = self.get_activity(activity_name)
        if activity:
            queues = set()
            for arc in activity.at_end:
                for p in arc.produce:
                    queues.add(p.queue)
            return list(queues)
        return []

    def validate_model(self) -> List[str]:
        """Validate the ACD model structure. Returns list of errors."""
        errors = []
        queue_names = set(self.queues.keys())
        activity_names = {a.name for a in self.activities}

        # Check all consumed queues exist
        for activity in self.activities:
            for consume in activity.at_begin.consume:
                if consume.queue not in queue_names:
                    errors.append(
                        f"Activity '{activity.name}' consumes from unknown queue: {consume.queue}"
                    )

            # Check all produced queues exist
            for arc in activity.at_end:
                for produce in arc.produce:
                    if produce.queue not in queue_names:
                        errors.append(
                            f"Activity '{activity.name}' produces to unknown queue: {produce.queue}"
                        )

        # Check random streams referenced in durations exist
        for activity in self.activities:
            if isinstance(activity.duration, str):
                if activity.duration not in self.random_streams:
                    if activity.duration not in self.parameters:
                        if activity.duration not in self.state_variables:
                            # Could be an expression - skip validation
                            pass

        # Check token types referenced in queues exist
        defined_types = set(self.token_types.keys()) | {"Token", "Resource", "Job"}
        for queue_name, queue in self.queues.items():
            if queue.token_type not in defined_types:
                errors.append(
                    f"Queue '{queue_name}' uses undefined token type: {queue.token_type}"
                )

        return errors

    def get_enabling_condition(self, activity_name: str) -> str:
        """
        Generate the enabling condition for an activity.

        An activity is enabled iff:
        1. All input queues have sufficient tokens (marking(q) >= W⁻(a,q))
        2. The guard condition G(a) evaluates to true
        """
        activity = self.get_activity(activity_name)
        if not activity:
            return "false"

        conditions = []

        # Token availability conditions
        for consume in activity.at_begin.consume:
            conditions.append(f"marking({consume.queue}) >= {consume.count}")

        # Guard condition
        if activity.at_begin.condition != "true":
            conditions.append(activity.at_begin.condition)

        if not conditions:
            return "true"

        return " and ".join(conditions)


# =============================================================================
# ABSTRACT STATE CHANGE OPERATIONS (Pure JSON format)
# =============================================================================

class IncrementOp(BaseModel):
    """Increment a counter variable."""
    op: Literal["increment"] = "increment"
    var: str = Field(description="Variable name to increment")
    amount: Union[int, str] = Field(default=1, description="Amount to increment by")


class DecrementOp(BaseModel):
    """Decrement a counter variable."""
    op: Literal["decrement"] = "decrement"
    var: str = Field(description="Variable name to decrement")
    amount: Union[int, str] = Field(default=1, description="Amount to decrement by")


class SetOp(BaseModel):
    """Set a variable to a value."""
    op: Literal["set"] = "set"
    var: str = Field(description="Variable name")
    value: Union[str, int, float, bool] = Field(description="Value to set")


class SetAttributeOp(BaseModel):
    """Set an attribute on an entity/token."""
    op: Literal["set_attribute"] = "set_attribute"
    entity: str = Field(description="Entity/token variable name")
    attribute: str = Field(description="Attribute name")
    value: Union[str, int, float] = Field(description="Value expression")


class ComputeOp(BaseModel):
    """Compute a value and store in a local variable."""
    op: Literal["compute"] = "compute"
    var: str = Field(description="Local variable name")
    expression: str = Field(description="Expression to compute")


class AccumulateOp(BaseModel):
    """Add a value to an accumulator for statistics."""
    op: Literal["accumulate"] = "accumulate"
    var: str = Field(description="Accumulator variable name")
    value: str = Field(description="Value expression to accumulate")


# Union type for all state change operations
StateChangeOp = Union[
    IncrementOp,
    DecrementOp,
    SetOp,
    SetAttributeOp,
    ComputeOp,
    AccumulateOp,
    Dict[str, Any],  # Fallback for simple dict-based operations
]


# =============================================================================
# JSON LOADING FUNCTIONS
# =============================================================================

def load_acd_from_json(json_path: str) -> "ACDSpec":
    """Load an ACD specification from a JSON file."""
    import json
    with open(json_path, 'r') as f:
        data = json.load(f)
    return parse_pure_acd_json(data)


def parse_pure_acd_json(data: Dict[str, Any]) -> "ACDSpec":
    """Parse pure ACD JSON data into an ACDSpec."""

    # Parse parameters
    parameters = {}
    for name, param_data in data.get("parameters", {}).items():
        parameters[name] = ParameterSpec(
            type=VariableType(param_data["type"]),
            value=param_data["value"],
            description=param_data.get("description")
        )

    # Parse token types
    token_types = {}
    for name, tt_data in data.get("token_types", {}).items():
        attributes = {}
        for attr_name, attr_data in tt_data.get("attributes", {}).items():
            if isinstance(attr_data, dict):
                attributes[attr_name] = TokenAttributeSpec(
                    type=VariableType(attr_data["type"]),
                    description=attr_data.get("description")
                )
            else:
                attributes[attr_name] = TokenAttributeSpec(type=VariableType(attr_data))

        token_types[name] = TokenTypeSpec(
            name=name,
            parent=tt_data.get("parent", "Token"),
            attributes=attributes,
            description=tt_data.get("description")
        )

    # Parse queues
    queues = {}
    for name, q_data in data.get("queues", {}).items():
        initial = q_data.get("initial_tokens", 0)
        # Handle string references like "num_servers"
        if isinstance(initial, str):
            # Will be resolved at runtime
            initial = 0  # Default for schema validation
        queues[name] = QueueSpec(
            initial_tokens=initial if isinstance(initial, int) else 0,
            token_type=q_data.get("token_type", "Token"),
            is_resource=q_data.get("is_resource", False),
            description=q_data.get("description")
        )

    # Parse activities
    activities = []
    for act_data in data.get("activities", []):
        # Parse at-begin
        at_begin_data = act_data.get("at_begin", {})
        consume_list = []
        for c in at_begin_data.get("consume", []):
            consume_list.append(TokenConsumeSpec(
                queue=c["queue"],
                count=c.get("count", 1),
                bind_as=c.get("bind_as")
            ))

        at_begin = AtBeginSpec(
            condition=at_begin_data.get("condition", "true"),
            consume=consume_list,
            actions=_parse_actions(at_begin_data.get("actions", []))
        )

        # Parse at-end arcs
        at_end_arcs = []
        for arc_data in act_data.get("at_end", []):
            produce_list = []
            for p in arc_data.get("produce", []):
                produce_list.append(TokenProduceSpec(
                    queue=p["queue"],
                    count=p.get("count", 1),
                    token_source=p.get("token_source"),
                    condition=p.get("condition", "true")
                ))

            at_end_arcs.append(AtEndArcSpec(
                condition=arc_data.get("condition", "true"),
                produce=produce_list,
                actions=_parse_actions(arc_data.get("actions", []))
            ))

        activities.append(ActivitySpec(
            name=act_data["name"],
            priority=act_data.get("priority", 0),
            duration=act_data["duration"],
            at_begin=at_begin,
            at_end=at_end_arcs,
            description=act_data.get("description")
        ))

    # Parse random streams
    random_streams = {}
    for name, rs_data in data.get("random_streams", {}).items():
        random_streams[name] = RandomStreamSpec(
            distribution=DistributionType(rs_data["distribution"]),
            params=rs_data.get("params", {}),
            stream_name=rs_data.get("stream_name")
        )

    # Parse state variables
    state_variables = {}
    for name, sv_data in data.get("state_variables", {}).items():
        if isinstance(sv_data, dict):
            state_variables[name] = sv_data
        else:
            state_variables[name] = {"type": "Nat", "initial": sv_data}

    # Parse observables
    observables = {}
    for name, obs_data in data.get("observables", {}).items():
        observables[name] = ObservableSpec(
            name=obs_data.get("name", name),
            expression=obs_data["expression"],
            description=obs_data.get("description")
        )

    # Parse statistics
    statistics = []
    for stat_data in data.get("statistics", []):
        statistics.append(StatisticSpec(
            name=stat_data["name"],
            type=stat_data["type"],
            expression=stat_data.get("expression", stat_data.get("observable", "")),
            description=stat_data.get("description")
        ))

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
        statistics=statistics
    )


def _parse_actions(actions_data: List[Any]) -> List[str]:
    """Parse action specifications into SimASM-compatible strings."""
    result = []
    for action in actions_data:
        if isinstance(action, str):
            result.append(action)
        elif isinstance(action, dict):
            op_type = action.get("op")
            if op_type == "increment":
                var = action["var"]
                amount = action.get("amount", 1)
                if amount == 1:
                    result.append(f"{var} := {var} + 1")
                else:
                    result.append(f"{var} := {var} + {amount}")
            elif op_type == "decrement":
                var = action["var"]
                amount = action.get("amount", 1)
                if amount == 1:
                    result.append(f"{var} := {var} - 1")
                else:
                    result.append(f"{var} := {var} - {amount}")
            elif op_type == "set":
                result.append(f"{action['var']} := {action['value']}")
            elif op_type == "set_attribute":
                result.append(f"{action['attribute']}({action['entity']}) := {action['value']}")
            elif op_type == "compute":
                result.append(f"let {action['var']} = {action['expression']}")
            elif op_type == "accumulate":
                var = action["var"]
                value = action["value"]
                result.append(f"{var} := {var} + {value}")
    return result


# =============================================================================
# EXAMPLE FACTORY
# =============================================================================

def create_mm5_acd_spec() -> ACDSpec:
    """
    Create an example ACD specification for M/M/5 queue.

    This matches the structure in mm5_acd.simasm with fine-grained semantics.
    """
    return ACDSpec(
        model_name="mm5_acd",
        description="M/M/5 Queue using Activity Cycle Diagram formalism (fine-grained)",

        parameters={
            "num_servers": ParameterSpec(type=VariableType.NAT, value=5),
            "iat_mean": ParameterSpec(type=VariableType.REAL, value=1.25),
            "ist_mean": ParameterSpec(type=VariableType.REAL, value=1.0),
            "sim_end_time": ParameterSpec(type=VariableType.REAL, value=1000.0),
        },

        token_types={
            "Job": TokenTypeSpec(
                name="Job",
                parent="Token",
                attributes={
                    "arrival_time": TokenAttributeSpec(type=VariableType.REAL),
                    "service_start_time": TokenAttributeSpec(type=VariableType.REAL),
                },
                description="Customer job token"
            ),
            "Resource": TokenTypeSpec(
                name="Resource",
                parent="Token",
                description="Reusable resource token (creator, server)"
            ),
        },

        queues={
            "C": QueueSpec(
                initial_tokens=1,
                token_type="Resource",
                is_resource=True,
                description="Creator resource queue"
            ),
            "Q": QueueSpec(
                initial_tokens=0,
                token_type="Job",
                description="Job waiting queue"
            ),
            "S": QueueSpec(
                initial_tokens=5,  # num_servers
                token_type="Resource",
                is_resource=True,
                description="Server resource queue"
            ),
            "Jobs": QueueSpec(
                initial_tokens=0,
                token_type="Job",
                description="Completed jobs (sink)"
            ),
        },

        activities=[
            ActivitySpec(
                name="Create",
                priority=1,  # Scan first (arrivals before service)
                duration="duration_create",
                at_begin=AtBeginSpec(
                    consume=[
                        TokenConsumeSpec(queue="C", count=1, bind_as="creator_token")
                    ]
                ),
                at_end=[
                    AtEndArcSpec(
                        condition="true",
                        produce=[
                            TokenProduceSpec(
                                queue="C", count=1,
                                token_source="creator_token"
                            ),
                            TokenProduceSpec(
                                queue="Q", count=1,
                                token_source="new"
                            ),
                        ],
                        actions=[
                            "job_id_counter := job_id_counter + 1",
                            "arrival_time(new_job) := sim_clocktime",
                        ]
                    )
                ],
                description="Job creation activity"
            ),
            ActivitySpec(
                name="Serve",
                priority=2,  # Scan after Create
                duration="duration_serve",
                at_begin=AtBeginSpec(
                    consume=[
                        TokenConsumeSpec(queue="S", count=1, bind_as="server_token"),
                        TokenConsumeSpec(queue="Q", count=1, bind_as="job_token"),
                    ],
                    actions=[
                        "service_start_time(job_token) := sim_clocktime",
                    ]
                ),
                at_end=[
                    AtEndArcSpec(
                        condition="true",
                        produce=[
                            TokenProduceSpec(
                                queue="S", count=1,
                                token_source="server_token"
                            ),
                            TokenProduceSpec(
                                queue="Jobs", count=1,
                                token_source="job_token"
                            ),
                        ],
                        actions=[
                            "departure_count := departure_count + 1",
                            "total_sojourn_time := total_sojourn_time + (sim_clocktime - arrival_time(job_token))",
                        ]
                    )
                ],
                description="Service activity"
            ),
        ],

        random_streams={
            "duration_create": RandomStreamSpec(
                distribution=DistributionType.EXPONENTIAL,
                params={"mean": "iat_mean"},
                stream_name="arrivals"
            ),
            "duration_serve": RandomStreamSpec(
                distribution=DistributionType.EXPONENTIAL,
                params={"mean": "ist_mean"},
                stream_name="service"
            ),
        },

        state_variables={
            "job_id_counter": {"type": "Nat", "initial": 0},
            "departure_count": {"type": "Nat", "initial": 0},
            "total_sojourn_time": {"type": "Real", "initial": 0.0},
            "total_time_in_queue": {"type": "Real", "initial": 0.0},
        },

        stopping_condition="sim_clocktime >= sim_end_time",

        observables={
            "queue_count": ObservableSpec(
                name="queue_count",
                expression="marking(Q)",
                description="Number in queue"
            ),
            "servers_busy": ObservableSpec(
                name="servers_busy",
                expression="num_servers - marking(S)",
                description="Number of busy servers"
            ),
            "in_system": ObservableSpec(
                name="in_system",
                expression="marking(Q) + (num_servers - marking(S))",
                description="Total in system"
            ),
        },

        statistics=[
            StatisticSpec(
                name="L_q",
                type="time_average",
                expression="marking(Q)",
                description="Average queue length"
            ),
            StatisticSpec(
                name="L",
                type="time_average",
                expression="marking(Q) + (num_servers - marking(S))",
                description="Average number in system"
            ),
            StatisticSpec(
                name="throughput",
                type="count",
                expression="departure_count",
                description="Total departures"
            ),
        ]
    )
