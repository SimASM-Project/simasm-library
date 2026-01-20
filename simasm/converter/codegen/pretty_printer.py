"""
Pretty Printer for SimASM Code Generation

Converts structured representations (schemas, templates) to formatted
SimASM source code text.
"""

from typing import List, Dict, Any, Optional, Union
from datetime import datetime


class PrettyPrinter:
    """
    Pretty printer for generating SimASM source code.

    Handles indentation, comments, and formatting according to
    SimASM conventions.
    """

    def __init__(self, indent_str: str = "    "):
        self.indent_str = indent_str
        self.indent_level = 0
        self.lines: List[str] = []

    def reset(self):
        """Reset the printer state."""
        self.indent_level = 0
        self.lines = []

    def indent(self):
        """Increase indentation level."""
        self.indent_level += 1

    def dedent(self):
        """Decrease indentation level."""
        self.indent_level = max(0, self.indent_level - 1)

    def _get_indent(self) -> str:
        """Get current indentation string."""
        return self.indent_str * self.indent_level

    def line(self, text: str = ""):
        """Add a line with current indentation."""
        if text:
            self.lines.append(f"{self._get_indent()}{text}")
        else:
            self.lines.append("")

    def comment(self, text: str):
        """Add a comment line."""
        self.line(f"// {text}")

    def block_comment(self, text: str, width: int = 77):
        """Add a block comment with separator lines."""
        separator = "=" * width
        self.line(f"// {separator}")
        self.line(f"// {text}")
        self.line(f"// {separator}")

    def section_comment(self, text: str, width: int = 77):
        """Add a section comment with dashes."""
        separator = "-" * width
        self.line(f"// {separator}")
        self.line(f"// {text}")
        self.line(f"// {separator}")

    def blank(self):
        """Add a blank line."""
        self.lines.append("")

    def get_output(self) -> str:
        """Get the complete output as a string."""
        return "\n".join(self.lines)

    # =========================================================================
    # HIGH-LEVEL GENERATION METHODS
    # =========================================================================

    def write_header(self, model_name: str, description: Optional[str] = None,
                     formalism: str = "Event Graph"):
        """Write the file header comment."""
        self.block_comment(f"{formalism} Model: {model_name} - SimASM")
        if description:
            # Handle multiline descriptions
            for line in description.split('\n'):
                self.comment(line)
        self.comment(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.blank()

    def write_imports(self, imports: List[tuple] = None):
        """Write import declarations."""
        if imports is None:
            imports = [("Random", "rnd"), ("Stdlib", "lib")]

        self.block_comment("IMPORT LIBRARIES")
        self.blank()
        for module, alias in imports:
            self.line(f"import {module} as {alias}")
        self.blank()

    def write_domain(self, name: str, parent: Optional[str] = None):
        """Write a domain declaration."""
        if parent:
            self.line(f"domain {name} <: {parent}")
        else:
            self.line(f"domain {name}")

    def write_const(self, name: str, type_str: str, comment: Optional[str] = None):
        """Write a constant declaration."""
        line = f"const {name}: {type_str}"
        if comment:
            line += f"  // {comment}"
        self.line(line)

    def write_var(self, name: str, type_str: str, comment: Optional[str] = None):
        """Write a variable declaration."""
        line = f"var {name}: {type_str}"
        if comment:
            line += f"  // {comment}"
        self.line(line)

    def write_random_stream(self, name: str, distribution: str,
                            params: Dict[str, Any], stream_name: Optional[str] = None):
        """Write a random stream variable declaration."""
        param_str = ", ".join(f"{v}" for v in params.values())
        if stream_name:
            self.line(f"var {name}: rnd.{distribution}({param_str}) as \"{stream_name}\"")
        else:
            self.line(f"var {name}: rnd.{distribution}({param_str})")

    def write_static_func(self, name: str, params: List[tuple], return_type: str):
        """Write a static function declaration."""
        param_str = ", ".join(f"{p}: {t}" for p, t in params)
        self.line(f"static function {name}({param_str}): {return_type}")

    def write_dynamic_func(self, name: str, params: List[tuple], return_type: str):
        """Write a dynamic function declaration."""
        param_str = ", ".join(f"{p}: {t}" for p, t in params)
        self.line(f"dynamic function {name}({param_str}): {return_type}")

    def write_derived_func(self, name: str, params: List[tuple],
                           return_type: str, body: str):
        """Write a derived function declaration."""
        param_str = ", ".join(f"{p}: {t}" for p, t in params) if params else ""
        self.line(f"derived function {name}({param_str}): {return_type} =")
        self.indent()
        self.line(body)
        self.dedent()

    def write_rule_start(self, name: str, params: List[tuple] = None):
        """Write the start of a rule declaration."""
        param_str = ""
        if params:
            param_str = ", ".join(f"{p}: {t}" for p, t in params)
        self.line(f"rule {name}({param_str}) =")
        self.indent()

    def write_rule_end(self):
        """Write the end of a rule declaration."""
        self.dedent()
        self.line("endrule")

    def write_main_rule_start(self, name: str = "main"):
        """Write the start of the main rule."""
        self.line(f"main rule {name} =")
        self.indent()

    def write_main_rule_end(self):
        """Write the end of the main rule."""
        self.dedent()
        self.line("endrule")

    def write_init_start(self):
        """Write the start of the init block."""
        self.line("init:")
        self.indent()

    def write_init_end(self):
        """Write the end of the init block."""
        self.dedent()
        self.line("endinit")

    def write_if(self, condition: str):
        """Write an if statement start."""
        self.line(f"if {condition} then")
        self.indent()

    def write_elseif(self, condition: str):
        """Write an elseif clause."""
        self.dedent()
        self.line(f"elseif {condition} then")
        self.indent()

    def write_else(self):
        """Write an else clause."""
        self.dedent()
        self.line("else")
        self.indent()

    def write_endif(self):
        """Write endif."""
        self.dedent()
        self.line("endif")

    def write_update(self, target: str, expression: str):
        """Write an update statement."""
        self.line(f"{target} := {expression}")

    def write_let(self, var_name: str, expression: str):
        """Write a let statement."""
        self.line(f"let {var_name} = {expression}")

    def write_new(self, var_name: str, domain: str):
        """Write a new object creation."""
        self.line(f"let {var_name} = new {domain}")

    def write_lib_call(self, func: str, *args):
        """Write a library function call."""
        args_str = ", ".join(str(a) for a in args)
        self.line(f"lib.{func}({args_str})")

    def write_rule_call(self, name: str, *args):
        """Write a rule call."""
        args_str = ", ".join(str(a) for a in args)
        self.line(f"{name}({args_str})")

    def write_raw(self, text: str):
        """Write raw text with current indentation."""
        for line in text.split("\n"):
            self.line(line)
