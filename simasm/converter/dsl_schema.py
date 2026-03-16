"""Schema definitions for the converter DSL."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union


class FormalismType(str, Enum):
    """Supported formalism types for conversion."""

    EVENT_GRAPH = "event_graph"
    ACD = "acd"
    DEVS = "devs"


@dataclass
class ConvertSpec:
    """Specification for a convert block.

    Attributes:
        name: The identifier for this convert block
        source: Path to the JSON source file
        formalism: The formalism type (event_graph or acd)
        register: Optional model name to register in the model registry
        print_lines: Number of lines to print (True=all, False=none, int=N lines)
        output: Optional file path to write the generated SimASM code
    """

    name: str
    source: str
    formalism: FormalismType
    register: Optional[str] = None
    print_lines: Union[int, bool] = True
    output: Optional[str] = None
