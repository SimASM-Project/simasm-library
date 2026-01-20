"""Engine for executing convert specifications."""

import json
from pathlib import Path
from typing import List, Optional, Tuple

from .parser import ConvertParser
from .dsl_schema import ConvertSpec, FormalismType


class ConvertResult:
    """Result of a convert operation."""

    def __init__(
        self,
        name: str,
        simasm_code: str,
        registered_as: Optional[str] = None,
        output_path: Optional[str] = None,
    ):
        self.name = name
        self.simasm_code = simasm_code
        self.registered_as = registered_as
        self.output_path = output_path


class ConvertEngine:
    """Engine for executing convert DSL specifications."""

    def __init__(self, base_path: Optional[Path] = None, model_registry: Optional[dict] = None):
        """Initialize the convert engine.

        Args:
            base_path: Base path for resolving relative file paths.
                      If None, uses current working directory.
            model_registry: Optional model registry dict to register models into.
                           If None, models won't be registered.
        """
        self._parser = ConvertParser()
        self._base_path = base_path or Path.cwd()
        self._model_registry = model_registry

    def execute(self, code: str) -> List[ConvertResult]:
        """Execute convert DSL code.

        Args:
            code: The convert DSL code to execute

        Returns:
            List of ConvertResult objects
        """
        specs = self._parser.parse(code)
        results = []

        for spec in specs:
            result = self._execute_spec(spec)
            results.append(result)

        return results

    def _execute_spec(self, spec: ConvertSpec) -> ConvertResult:
        """Execute a single convert specification.

        Args:
            spec: The ConvertSpec to execute

        Returns:
            ConvertResult with the generated code
        """
        # Load JSON source
        source_path = self._resolve_path(spec.source)
        with open(source_path, "r") as f:
            json_data = json.load(f)

        # Convert based on formalism
        simasm_code = self._convert(json_data, spec.formalism)

        # Register model if requested
        registered_as = None
        if spec.register and self._model_registry is not None:
            self._model_registry[spec.register] = simasm_code
            registered_as = spec.register

        # Write output if requested
        output_path = None
        if spec.output:
            output_path = self._resolve_path(spec.output)
            with open(output_path, "w") as f:
                f.write(simasm_code)

        return ConvertResult(
            name=spec.name,
            simasm_code=simasm_code,
            registered_as=registered_as,
            output_path=str(output_path) if output_path else None,
        )

    def _convert(self, json_data: dict, formalism: FormalismType) -> str:
        """Convert JSON data to SimASM code.

        Args:
            json_data: The JSON specification
            formalism: The formalism type

        Returns:
            Generated SimASM code
        """
        if formalism == FormalismType.EVENT_GRAPH:
            from simasm.converter.event_graph.schema import EventGraphSpec
            from simasm.converter.event_graph.converter import convert_eg

            spec = EventGraphSpec.from_dict(json_data)
            return convert_eg(spec)

        elif formalism == FormalismType.ACD:
            from simasm.converter.acd.schema import ACDSpec
            from simasm.converter.acd.converter import convert_acd

            spec = ACDSpec.from_dict(json_data)
            return convert_acd(spec)

        else:
            raise ValueError(f"Unsupported formalism: {formalism}")

    def _resolve_path(self, path_str: str) -> Path:
        """Resolve a path relative to the base path.

        Args:
            path_str: The path string to resolve

        Returns:
            Resolved absolute Path
        """
        path = Path(path_str)
        if path.is_absolute():
            return path
        return self._base_path / path


def format_output(
    result: ConvertResult,
    print_lines: int | bool,
) -> str:
    """Format the output for display.

    Args:
        result: The ConvertResult to format
        print_lines: True for all, False for none, int for N lines

    Returns:
        Formatted output string
    """
    lines = []

    # Header
    lines.append(f"// Convert: {result.name}")
    if result.registered_as:
        lines.append(f"// Registered as: {result.registered_as}")
    if result.output_path:
        lines.append(f"// Written to: {result.output_path}")
    lines.append("")

    # Code output
    if print_lines is False:
        lines.append("// (output suppressed)")
    elif print_lines is True:
        lines.append(result.simasm_code)
    else:
        # Print first N lines
        code_lines = result.simasm_code.split("\n")
        if len(code_lines) <= print_lines:
            lines.append(result.simasm_code)
        else:
            lines.extend(code_lines[:print_lines])
            lines.append(f"// ... ({len(code_lines) - print_lines} more lines)")

    return "\n".join(lines)
