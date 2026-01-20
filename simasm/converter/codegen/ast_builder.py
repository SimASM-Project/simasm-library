"""
AST Builder Utilities

Provides helper functions for building SimASM AST nodes programmatically.
This module bridges between the JSON schema representations and the
SimASM parser AST.
"""

from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass


@dataclass
class TypeExpr:
    """Simple type expression representation."""
    name: str
    param: Optional[str] = None


@dataclass
class FuncParam:
    """Function parameter representation."""
    name: str
    type_expr: TypeExpr


class ASTBuilder:
    """
    Helper class for building SimASM code structures.

    This class provides utilities for constructing the intermediate
    representation that gets serialized to SimASM text.
    """

    @staticmethod
    def simple_type(name: str) -> TypeExpr:
        """Create a simple type expression."""
        return TypeExpr(name=name)

    @staticmethod
    def list_type(element_type: str) -> TypeExpr:
        """Create a List<T> type expression."""
        return TypeExpr(name="List", param=element_type)

    @staticmethod
    def param(name: str, type_name: str) -> FuncParam:
        """Create a function parameter."""
        return FuncParam(name=name, type_expr=TypeExpr(name=type_name))

    @staticmethod
    def parse_type_string(type_str: str) -> TypeExpr:
        """Parse a type string like 'List<Event>' into a TypeExpr."""
        if "<" in type_str:
            base = type_str[:type_str.index("<")]
            param = type_str[type_str.index("<")+1:type_str.rindex(">")]
            return TypeExpr(name=base, param=param)
        return TypeExpr(name=type_str)

    @staticmethod
    def format_type(type_expr: TypeExpr) -> str:
        """Format a TypeExpr back to string."""
        if type_expr.param:
            return f"{type_expr.name}<{type_expr.param}>"
        return type_expr.name

    @staticmethod
    def map_variable_type(type_enum: str) -> str:
        """Map VariableType enum to SimASM type string."""
        mapping = {
            "Nat": "Nat",
            "Int": "Int",
            "Real": "Real",
            "Bool": "Bool",
            "String": "String",
            "NAT": "Nat",
            "INT": "Int",
            "REAL": "Real",
            "BOOL": "Bool",
            "STRING": "String",
        }
        return mapping.get(type_enum, type_enum)

    @staticmethod
    def map_distribution(dist_enum: str) -> str:
        """Map DistributionType enum to rnd.* function name."""
        mapping = {
            "exponential": "exponential",
            "uniform": "uniform",
            "normal": "normal",
            "triangular": "triangular",
            "constant": "constant",
            "empirical": "empirical",
            "EXPONENTIAL": "exponential",
            "UNIFORM": "uniform",
            "NORMAL": "normal",
            "TRIANGULAR": "triangular",
            "CONSTANT": "constant",
            "EMPIRICAL": "empirical",
        }
        return mapping.get(dist_enum, dist_enum)

    @staticmethod
    def format_value(value: Any) -> str:
        """Format a Python value as SimASM literal."""
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, str):
            # Check if it's a reference or a string literal
            if value.startswith('"') or value.startswith("'"):
                return value
            # Assume it's a reference
            return value
        elif isinstance(value, float):
            return str(value)
        elif isinstance(value, int):
            return str(value)
        elif value is None:
            return "undef"
        else:
            return str(value)

    @staticmethod
    def format_string_literal(value: str) -> str:
        """Format a string as a SimASM string literal."""
        return f'"{value}"'

    @staticmethod
    def indent_code(code: str, levels: int = 1, indent_str: str = "    ") -> str:
        """Indent a block of code."""
        indent = indent_str * levels
        lines = code.split("\n")
        return "\n".join(indent + line if line.strip() else line for line in lines)

    @staticmethod
    def join_conditions(conditions: List[str], operator: str = "and") -> str:
        """Join multiple conditions with an operator."""
        if not conditions:
            return "true"
        if len(conditions) == 1:
            return conditions[0]
        return f" {operator} ".join(f"({c})" for c in conditions)
