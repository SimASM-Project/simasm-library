"""
Event Graph to SimASM Converter

Converts Event Graph specifications in JSON format to SimASM code.
Based on Schruben (1983) Event Graph methodology and the formal
transformation proof in "Transformation of Event Graphs to ASM".
"""

from .schema import EventGraphSpec
from .converter import EventGraphConverter, convert_eg, convert_eg_from_json

__all__ = [
    "EventGraphSpec",
    "EventGraphConverter",
    "convert_eg",
    "convert_eg_from_json",
]
