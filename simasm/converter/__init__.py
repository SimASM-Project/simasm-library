"""SimASM Converter Module.

This module provides:
1. Converters from high-level simulation formalisms (Event Graph, ACD)
   specified in JSON to SimASM code.
2. DSL-based conversion via %%simasm convert magic command.

The converters implement fine-grained step semantics for trace equivalence
between different formalisms.

Usage:
    # Direct Python API
    from simasm.converter.event_graph.schema import EventGraphSpec
    from simasm.converter.event_graph.converter import convert_eg

    from simasm.converter.acd.schema import ACDSpec
    from simasm.converter.acd.converter import convert_acd

    # Or via simasm API
    import simasm
    simasm.convert_model("mm5_eg.json", formalism="event_graph", register_as="mm5_eg")

    # Or via Jupyter magic
    %%simasm convert

    convert mm5_eg:
        source: "mm5_eg.json"
        formalism: event_graph
        register: "mm5_eg"
        print: 50
    endconvert
"""

# DSL-based conversion
from .dsl_schema import ConvertSpec, FormalismType
from .parser import ConvertParser
from .engine import ConvertEngine

# Event Graph converters
from .event_graph.schema import EventGraphSpec
from .event_graph.converter import convert_eg, convert_eg_from_json, EventGraphConverter

# ACD converters
from .acd.schema import ACDSpec
from .acd.converter import convert_acd, convert_acd_from_json, ACDConverter

__all__ = [
    # DSL conversion
    "ConvertSpec", "FormalismType", "ConvertParser", "ConvertEngine",
    # Event Graph
    "EventGraphSpec", "EventGraphConverter", "convert_eg", "convert_eg_from_json",
    # ACD
    "ACDSpec", "ACDConverter", "convert_acd", "convert_acd_from_json",
]
