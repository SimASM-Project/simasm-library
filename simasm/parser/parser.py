"""
parser/parser.py

High-level parser API for SimASM.

Provides:
- SimASMParser: Main parser class with convenient methods
- parse_file: Parse a .simasm file to Program AST
- parse_string: Parse source code string to Program AST
"""

from pathlib import Path
from typing import Optional, Union

from lark import Lark, LarkError

from simasm.parser.transformer import SimASMTransformer
from simasm.parser.ast import Program


# ============================================================================
# Parser Class
# ============================================================================

class ParseError(Exception):
    """Raised when parsing fails."""
    pass


class SimASMParser:
    """
    High-level parser for SimASM programs.
    
    Parses SimASM source code into Program AST nodes.
    
    Usage:
        parser = SimASMParser()
        
        # Parse from string
        program = parser.parse("domain Load\\nvar x: Int")
        
        # Parse from file
        program = parser.parse_file("model.simasm")
    
    The parser is reusable - create once, parse many files.
    """
    
    # Grammar file location (relative to this module)
    GRAMMAR_FILE = Path(__file__).parent / "grammar.lark"
    
    def __init__(self):
        """
        Create parser.
        
        Loads grammar and creates Lark parser with transformer.
        """
        self._grammar = self._load_grammar()
        self._transformer = SimASMTransformer()
        self._parser = Lark(
            self._grammar,
            start="program",
            parser="lalr",
            transformer=self._transformer
        )
    
    def _load_grammar(self) -> str:
        """Load grammar from file."""
        if not self.GRAMMAR_FILE.exists():
            raise ParseError(f"Grammar file not found: {self.GRAMMAR_FILE}")
        return self.GRAMMAR_FILE.read_text()
    
    def parse(self, source: str, filename: Optional[str] = None) -> Program:
        """
        Parse SimASM source code.
        
        Args:
            source: SimASM source code string
            filename: Optional filename for error messages
            
        Returns:
            Program AST
            
        Raises:
            ParseError: If parsing fails
        """
        try:
            return self._parser.parse(source)
        except LarkError as e:
            if filename:
                raise ParseError(f"Error parsing {filename}: {e}") from e
            raise ParseError(f"Parse error: {e}") from e
    
    def parse_file(self, path: Union[str, Path]) -> Program:
        """
        Parse SimASM file.
        
        Args:
            path: Path to .simasm file
            
        Returns:
            Program AST
            
        Raises:
            ParseError: If file not found or parsing fails
        """
        path = Path(path)
        
        if not path.exists():
            raise ParseError(f"File not found: {path}")
        
        source = path.read_text()
        return self.parse(source, filename=str(path))


# ============================================================================
# Convenience Functions
# ============================================================================

# Singleton parser instance (lazy initialization)
_parser: Optional[SimASMParser] = None


def _get_parser() -> SimASMParser:
    """Get or create singleton parser."""
    global _parser
    if _parser is None:
        _parser = SimASMParser()
    return _parser


def parse_string(source: str) -> Program:
    """
    Parse SimASM source code string.
    
    Convenience function using shared parser instance.
    
    Args:
        source: SimASM source code
        
    Returns:
        Program AST
        
    Example:
        from simasm.parser import parse_string
        
        program = parse_string('''
            domain Load
            var counter: Int
            
            rule increment() =
                counter := counter + 1
            endrule
        ''')
    """
    return _get_parser().parse(source)


def parse_file(path: Union[str, Path]) -> Program:
    """
    Parse SimASM file.
    
    Convenience function using shared parser instance.
    
    Args:
        path: Path to .simasm file
        
    Returns:
        Program AST
        
    Example:
        from simasm.parser import parse_file
        
        program = parse_file("models/mm1_queue.simasm")
    """
    return _get_parser().parse_file(path)
