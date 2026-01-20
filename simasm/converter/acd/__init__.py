"""
Activity Cycle Diagram to SimASM Converter

Converts Activity Cycle Diagram specifications in JSON format to SimASM code.
Based on Tocher (1960), Carrie (1988), and the formal transformation proof
in "Transformation of Activity Cycle Diagrams to ASM".

Implements fine-grained step semantics for trace equivalence with Event Graph:
- One ASM step = start ONE activity OR execute ONE BTO event
- Phase-based state machine: init → scan → time → execute → scan → ...
"""

from .schema import ACDSpec, load_acd_from_json, parse_acd_json
from .converter import ACDConverter, convert_acd, convert_acd_from_json

__all__ = [
    "ACDSpec",
    "ACDConverter",
    "convert_acd",
    "convert_acd_from_json",
    "load_acd_from_json",
    "parse_acd_json",
]
