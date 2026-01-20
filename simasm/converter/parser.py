"""Parser for the converter DSL."""

from pathlib import Path
from typing import List

from lark import Lark, Transformer, v_args

from .dsl_schema import ConvertSpec, FormalismType


class ConvertTransformer(Transformer):
    """Transforms the parse tree into ConvertSpec objects."""

    @v_args(inline=True)
    def start(self, *convert_decls) -> List[ConvertSpec]:
        """Return list of ConvertSpec objects."""
        return list(convert_decls)

    @v_args(inline=True)
    def convert_decl(self, name, body) -> ConvertSpec:
        """Build a ConvertSpec from parsed components."""
        return ConvertSpec(
            name=str(name),
            source=body.get("source", ""),
            formalism=body.get("formalism", FormalismType.EVENT_GRAPH),
            register=body.get("register"),
            print_lines=body.get("print_lines", True),
            output=body.get("output"),
        )

    def convert_body(self, settings) -> dict:
        """Merge all settings into a single dict."""
        result = {}
        for setting in settings:
            result.update(setting)
        return result

    def convert_setting(self, items) -> dict:
        """Pass through the setting dict."""
        return items[0]

    def source_setting(self, items) -> dict:
        """Extract source path."""
        return {"source": self._strip_quotes(items[0])}

    def formalism_setting(self, items) -> dict:
        """Extract formalism type."""
        formalism_str = str(items[0])
        return {"formalism": FormalismType(formalism_str)}

    def register_setting(self, items) -> dict:
        """Extract register name."""
        return {"register": self._strip_quotes(items[0])}

    def print_setting(self, items) -> dict:
        """Extract print configuration."""
        return {"print_lines": items[0]}

    def output_setting(self, items) -> dict:
        """Extract output path."""
        return {"output": self._strip_quotes(items[0])}

    def print_lines(self, items) -> int:
        """Parse print line count."""
        return int(items[0])

    def print_all(self, items) -> bool:
        """Parse print: true."""
        return True

    def print_none(self, items) -> bool:
        """Parse print: false."""
        return False

    def _strip_quotes(self, token) -> str:
        """Remove surrounding quotes from a string token."""
        s = str(token)
        if s.startswith('"') and s.endswith('"'):
            return s[1:-1]
        return s


class ConvertParser:
    """Parser for convert DSL code."""

    def __init__(self):
        """Initialize the parser with the grammar."""
        grammar_path = Path(__file__).parent / "grammar.lark"
        with open(grammar_path, "r") as f:
            grammar = f.read()

        self._parser = Lark(
            grammar,
            parser="lalr",
            transformer=ConvertTransformer(),
            start="start",
        )

    def parse(self, code: str) -> List[ConvertSpec]:
        """Parse convert DSL code into a list of ConvertSpec objects.

        Args:
            code: The convert DSL code to parse

        Returns:
            List of ConvertSpec objects
        """
        return self._parser.parse(code)
