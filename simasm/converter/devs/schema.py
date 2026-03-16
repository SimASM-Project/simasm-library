"""
Pydantic schema for DEVS JSON model specification.

Maps the algebraic specification:
  M = <X, Y, S, delta_ext, delta_int, lambda, ta>  (atomic)
  N = <X, Y, D, {M_d}, {I_d}, {Z_{i,d}}, Select>  (coupled)
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field


class ParameterSpec(BaseModel):
    type: str = "Real"
    value: Union[int, float]
    description: str = ""


class RandomStreamSpec(BaseModel):
    distribution: str
    params: Dict[str, Any]
    stream_name: str = ""


class StateSpec(BaseModel):
    """A state in a DEVS atomic model with its time advance."""
    name: str
    time_advance: Union[str, int, float]  # random stream name, numeric, or "infinity"


class StateVariableSpec(BaseModel):
    type: str = "Nat"
    initial: Union[int, float] = 0
    description: str = ""


class InternalTransitionSpec(BaseModel):
    """delta_int: S -> S"""
    from_state: str = Field(alias="from")
    to_state: str = Field(alias="to")
    condition: str = "true"
    state_change: str = ""

    model_config = {"populate_by_name": True}


class ExternalTransitionSpec(BaseModel):
    """delta_ext: Q x X -> S"""
    from_state: str = Field(alias="from")
    input_port: str
    to_state: str = Field(alias="to")
    condition: str = "true"
    state_change: str = ""

    model_config = {"populate_by_name": True}


class OutputSpec(BaseModel):
    """lambda: S -> Y"""
    state: str
    output_port: str
    value: str = ""
    condition: str = "true"  # optional condition for conditional output


class AtomicModelSpec(BaseModel):
    """DEVS atomic model specification: M = <X, Y, S, delta_ext, delta_int, lambda, ta>"""
    name: str
    description: str = ""
    inputs: List[str] = []
    outputs: List[str] = []
    states: List[StateSpec]
    initial_state: str
    state_variables: Dict[str, StateVariableSpec] = {}
    internal_transitions: List[InternalTransitionSpec]
    external_transitions: List[ExternalTransitionSpec] = []
    output_function: List[OutputSpec] = []


class CouplingSpec(BaseModel):
    """Internal coupling: Z_{i,d}(Y_i) -> X_d"""
    from_model: str
    from_port: str
    to_model: str
    to_port: str


class CoupledModelSpec(BaseModel):
    """DEVS coupled model specification: N = <X, Y, D, {M_d}, {I_d}, {Z_{i,d}}, Select>"""
    name: str
    components: List[str]
    internal_couplings: List[CouplingSpec]
    external_input_couplings: List[CouplingSpec] = []
    external_output_couplings: List[CouplingSpec] = []
    select_priority: List[str]  # ordered list for tie-breaking


class ObservableSpec(BaseModel):
    name: str
    expression: str
    description: str = ""


class StatisticSpec(BaseModel):
    name: str
    type: str  # "time_average" or "count"
    observable: str = ""
    expression: str = ""
    description: str = ""


class EntitySpec(BaseModel):
    name: str
    parent: str = "Object"
    attributes: Dict[str, str] = {}


class DEVSSpec(BaseModel):
    """Complete DEVS model specification (coupled model with atomic components)."""
    model_name: str
    description: str = ""
    entities: Dict[str, EntitySpec] = {}
    parameters: Dict[str, ParameterSpec] = {}
    random_streams: Dict[str, RandomStreamSpec] = {}
    atomic_models: List[AtomicModelSpec]
    coupled_model: CoupledModelSpec
    state_variables: Dict[str, StateVariableSpec] = {}
    observables: Dict[str, ObservableSpec] = {}
    statistics: List[StatisticSpec] = []
    stopping_condition: str = "sim_clocktime >= sim_end_time"

    @classmethod
    def from_dict(cls, data: dict) -> "DEVSSpec":
        return cls(**data)

    @classmethod
    def from_json(cls, path: str) -> "DEVSSpec":
        import json
        with open(path, 'r', encoding='utf-8') as f:
            return cls.from_dict(json.load(f))
