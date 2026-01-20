"""
SimASM parser module.

Provides parsing of SimASM source code into AST and loading into runtime.

Parsing API:
- parse_string(source) -> Program
- parse_file(path) -> Program
- SimASMParser class for advanced usage

Loading API:
- load_program(program) -> LoadedProgram
- load_string(source) -> LoadedProgram
- load_file(path) -> LoadedProgram

AST nodes:
- Program, RuleDecl, DomainDecl, etc.
"""

from simasm.parser.parser import (
    SimASMParser,
    ParseError,
    parse_string,
    parse_file,
)
from simasm.parser.loader import (
    ProgramLoader,
    LoadedProgram,
    LoadError,
    load_program,
    load_string,
    load_file,
)
from simasm.parser.ast import (
    # Type expressions
    TypeExpr, SimpleType, ParamType, Param,
    # Declarations
    Decl, ImportDecl, DomainDecl, ConstDecl, VarDecl,
    StaticFuncDecl, DynamicFuncDecl, DerivedFuncDecl,
    RuleDecl, MainRuleDecl, InitBlock,
    # Program
    Program,
)

__all__ = [
    # Parser API
    'SimASMParser',
    'ParseError',
    'parse_string',
    'parse_file',
    # Loader API
    'ProgramLoader',
    'LoadedProgram',
    'LoadError',
    'load_program',
    'load_string',
    'load_file',
    # Type expressions
    'TypeExpr', 'SimpleType', 'ParamType', 'Param',
    # Declarations
    'Decl', 'ImportDecl', 'DomainDecl', 'ConstDecl', 'VarDecl',
    'StaticFuncDecl', 'DynamicFuncDecl', 'DerivedFuncDecl',
    'RuleDecl', 'MainRuleDecl', 'InitBlock',
    # Program
    'Program',
]
