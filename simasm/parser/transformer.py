"""
parser/transformer.py

Transforms Lark parse tree into SimASM AST nodes.

This module provides:
- SimASMTransformer: Lark Transformer that converts parse trees to AST
"""

from typing import Any, List, Tuple, Optional
from lark import Transformer, Token, Tree

from simasm.core.state import UNDEF
from simasm.core.terms import (
    Term, LiteralTerm, VariableTerm, LocationTerm,
    BinaryOpTerm, UnaryOpTerm, ListTerm, TupleTerm,
    NewTerm, LibCallTerm, RndCallTerm,
)
from simasm.core.rules import (
    Stmt, SkipStmt, UpdateStmt, SeqStmt, IfStmt,
    WhileStmt, ForallStmt, LetStmt, RuleCallStmt, PrintStmt,
    ChooseStmt, ParStmt,
    LibCallStmt as LibCallStatement,
    RndCallStmt as RndCallStatement,
)
from simasm.parser.ast import (
    TypeExpr, SimpleType, ParamType, RndStreamType, Param,
    Decl, ImportDecl, DomainDecl, ConstDecl, VarDecl,
    StaticFuncDecl, DynamicFuncDecl, DerivedFuncDecl,
    RuleDecl, MainRuleDecl, InitBlock, Program,
)


class SimASMTransformer(Transformer):
    """
    Transforms Lark parse tree into SimASM AST nodes.
    
    Each method corresponds to a grammar rule and transforms
    its children into the appropriate AST node.
    """
    
    # ========================================================================
    # Terminals
    # ========================================================================
    
    def IDENTIFIER(self, token: Token) -> str:
        """Extract identifier string."""
        return str(token)
    
    def NUMBER(self, token: Token) -> LiteralTerm:
        """Convert number token to literal."""
        text = str(token)
        if '.' in text:
            return LiteralTerm(float(text))
        return LiteralTerm(int(text))
    
    def INTEGER(self, token: Token) -> LiteralTerm:
        """Convert integer token to literal."""
        return LiteralTerm(int(str(token)))
    
    def FLOAT(self, token: Token) -> LiteralTerm:
        """Convert float token to literal."""
        return LiteralTerm(float(str(token)))
    
    def STRING(self, token: Token) -> LiteralTerm:
        """Convert string token to literal (strip quotes)."""
        text = str(token)
        # Remove surrounding quotes
        return LiteralTerm(text[1:-1])
    
    # ========================================================================
    # Literals
    # ========================================================================
    
    def number(self, items: List) -> LiteralTerm:
        """Number literal - already converted by NUMBER terminal."""
        return items[0]
    
    def string(self, items: List) -> LiteralTerm:
        """String literal - already converted by STRING terminal."""
        return items[0]
    
    def true_lit(self, items: List) -> LiteralTerm:
        """Boolean true literal."""
        return LiteralTerm(True)
    
    def false_lit(self, items: List) -> LiteralTerm:
        """Boolean false literal."""
        return LiteralTerm(False)
    
    def undef_lit(self, items: List) -> LiteralTerm:
        """Undefined literal."""
        return LiteralTerm(UNDEF)
    
    # ========================================================================
    # Variables and Locations
    # ========================================================================
    
    def variable(self, items: List) -> VariableTerm:
        """Variable reference."""
        name = items[0]
        return VariableTerm(name)
    
    def func_app(self, items: List) -> LocationTerm:
        """Function application (location lookup)."""
        name = items[0]
        if len(items) > 1 and items[1] is not None:
            args = items[1]
        else:
            args = ()
        return LocationTerm(name, tuple(args))
    
    # ========================================================================
    # Operators
    # ========================================================================
    
    # Arithmetic operators
    def add_op(self, items: List) -> BinaryOpTerm:
        """Addition: a + b"""
        return BinaryOpTerm('+', items[0], items[1])
    
    def sub_op(self, items: List) -> BinaryOpTerm:
        """Subtraction: a - b"""
        return BinaryOpTerm('-', items[0], items[1])
    
    def mul_op(self, items: List) -> BinaryOpTerm:
        """Multiplication: a * b"""
        return BinaryOpTerm('*', items[0], items[1])
    
    def div_op(self, items: List) -> BinaryOpTerm:
        """Division: a / b"""
        return BinaryOpTerm('/', items[0], items[1])
    
    def mod_op(self, items: List) -> BinaryOpTerm:
        """Modulo: a % b"""
        return BinaryOpTerm('%', items[0], items[1])
    
    def neg_op(self, items: List) -> UnaryOpTerm:
        """Negation: -a"""
        return UnaryOpTerm('-', items[0])
    
    # Comparison operators
    def eq_op(self, items: List) -> BinaryOpTerm:
        """Equal: a == b"""
        return BinaryOpTerm('==', items[0], items[1])
    
    def ne_op(self, items: List) -> BinaryOpTerm:
        """Not equal: a != b"""
        return BinaryOpTerm('!=', items[0], items[1])
    
    def lt_op(self, items: List) -> BinaryOpTerm:
        """Less than: a < b"""
        return BinaryOpTerm('<', items[0], items[1])
    
    def gt_op(self, items: List) -> BinaryOpTerm:
        """Greater than: a > b"""
        return BinaryOpTerm('>', items[0], items[1])
    
    def le_op(self, items: List) -> BinaryOpTerm:
        """Less or equal: a <= b"""
        return BinaryOpTerm('<=', items[0], items[1])
    
    def ge_op(self, items: List) -> BinaryOpTerm:
        """Greater or equal: a >= b"""
        return BinaryOpTerm('>=', items[0], items[1])
    
    # Logical operators
    def and_op(self, items: List) -> BinaryOpTerm:
        """Logical and: a and b"""
        return BinaryOpTerm('and', items[0], items[1])
    
    def or_op(self, items: List) -> BinaryOpTerm:
        """Logical or: a or b"""
        return BinaryOpTerm('or', items[0], items[1])
    
    def not_op(self, items: List) -> UnaryOpTerm:
        """Logical not: not a"""
        return UnaryOpTerm('not', items[0])
    
    # ========================================================================
    # Collections
    # ========================================================================
    
    def empty_list(self, items: List) -> ListTerm:
        """Empty list: []"""
        return ListTerm(())
    
    def list_lit(self, items: List) -> ListTerm:
        """List literal: [a, b, c]"""
        return ListTerm(tuple(items))
    
    def tuple_expr(self, items: List) -> TupleTerm:
        """Tuple literal: (a, b, c)"""
        return TupleTerm(tuple(items))
    
    def arg_list(self, items: List) -> Tuple[Term, ...]:
        """Argument list for function calls."""
        return tuple(items)
    
    # ========================================================================
    # Function Calls
    # ========================================================================
    
    def lib_call(self, items: List) -> LibCallTerm:
        """Library call: lib.func(args)"""
        func_name = items[0]
        if len(items) > 1 and items[1] is not None:
            args = items[1]
        else:
            args = ()
        return LibCallTerm(func_name, tuple(args))
    
    def rnd_call_default(self, items: List) -> RndCallTerm:
        """Random call with default stream: rnd.func(args)"""
        func_name = items[0]
        if len(items) > 1 and items[1] is not None:
            args = items[1]
        else:
            args = ()
        return RndCallTerm(func_name, tuple(args), stream=None)
    
    def rnd_call_stream(self, items: List) -> RndCallTerm:
        """Random call with named stream: rnd.stream.func(args)"""
        stream_name = items[0]
        func_name = items[1]
        if len(items) > 2 and items[2] is not None:
            args = items[2]
        else:
            args = ()
        return RndCallTerm(func_name, tuple(args), stream=stream_name)
    
    def new_expr(self, items: List) -> NewTerm:
        """New expression: new Domain"""
        domain = items[0]
        return NewTerm(domain)
    
    # ========================================================================
    # Statements
    # ========================================================================
    
    def stmt_block(self, items: List) -> Stmt:
        """Statement block - sequence of statements."""
        if len(items) == 1:
            return items[0]
        return SeqStmt(tuple(items))
    
    def skip_stmt(self, items: List) -> SkipStmt:
        """Skip statement: skip"""
        return SkipStmt()
    
    def update_stmt(self, items: List) -> UpdateStmt:
        """Update statement: location := value"""
        location = items[0]
        value = items[1]
        # Ensure location is a LocationTerm
        if isinstance(location, VariableTerm):
            # Convert simple variable to 0-ary location
            location = LocationTerm(location.name, ())
        return UpdateStmt(location, value)
    
    def let_stmt(self, items: List) -> LetStmt:
        """Let binding: let x = expr"""
        var_name = items[0]
        value = items[1]
        return LetStmt(var_name, value)
    
    def if_stmt(self, items: List) -> IfStmt:
        """If statement: if cond then body [elseif ...]* [else ...] endif"""
        condition = items[0]
        then_body = items[1]
        
        # Collect elseif branches and else body
        elseif_branches = []
        else_body = None
        
        for item in items[2:]:
            if isinstance(item, tuple) and len(item) == 2:
                # elseif branch: (condition, body)
                elseif_branches.append(item)
            else:
                # else body
                else_body = item
        
        return IfStmt(
            condition=condition,
            then_body=then_body,
            elseif_branches=tuple(elseif_branches),
            else_body=else_body
        )
    
    def elseif_clause(self, items: List) -> Tuple[Term, Stmt]:
        """Elseif clause: elseif cond then body"""
        condition = items[0]
        body = items[1]
        return (condition, body)
    
    def else_clause(self, items: List) -> Stmt:
        """Else clause: else body"""
        return items[0]
    
    def while_stmt(self, items: List) -> WhileStmt:
        """While loop: while cond do body endwhile"""
        condition = items[0]
        body = items[1]
        return WhileStmt(condition, body)
    
    def forall_stmt(self, items: List) -> ForallStmt:
        """Forall: forall x in collection [with guard] do body endforall"""
        var_name = items[0]
        collection = items[1]
        
        # Check for optional guard
        if len(items) == 4:
            guard = items[2]
            body = items[3]
        else:
            guard = None
            body = items[2]
        
        return ForallStmt(var_name, collection, body, guard)
    
    def forall_guard(self, items: List) -> Term:
        """Forall guard: with condition"""
        return items[0]
    
    def choose_stmt(self, items: List) -> ChooseStmt:
        """Choose: choose x in collection [with guard] do body endchoose"""
        var_name = items[0]
        collection = items[1]
        
        # Check for optional guard
        if len(items) == 4:
            guard = items[2]
            body = items[3]
        else:
            guard = None
            body = items[2]
        
        return ChooseStmt(var_name, collection, body, guard)
    
    def par_stmt(self, items: List) -> ParStmt:
        """Parallel block: par body endpar"""
        body = items[0]
        return ParStmt(body)
    
    def rule_call_stmt(self, items: List) -> RuleCallStmt:
        """Rule call: name(args)"""
        name = items[0]
        if len(items) > 1 and items[1] is not None:
            args = items[1]
        else:
            args = ()
        # Rule name as a literal string term
        return RuleCallStmt(LiteralTerm(name), tuple(args))
    
    def lib_call_stmt(self, items: List) -> LibCallStatement:
        """Library call statement: lib.func(args)"""
        func_name = items[0]
        if len(items) > 1 and items[1] is not None:
            args = items[1]
        else:
            args = ()
        return LibCallStatement(func_name, tuple(args))
    
    def rnd_stmt_default(self, items: List) -> RndCallStatement:
        """Random call statement with default stream: rnd.func(args)"""
        func_name = items[0]
        if len(items) > 1 and items[1] is not None:
            args = items[1]
        else:
            args = ()
        return RndCallStatement(func_name, tuple(args), stream=None)
    
    def rnd_stmt_stream(self, items: List) -> RndCallStatement:
        """Random call statement with named stream: rnd.stream.func(args)"""
        stream_name = items[0]
        func_name = items[1]
        if len(items) > 2 and items[2] is not None:
            args = items[2]
        else:
            args = ()
        return RndCallStatement(func_name, tuple(args), stream=stream_name)
    
    def print_stmt(self, items: List) -> PrintStmt:
        """Print statement: print(expr)"""
        expression = items[0]
        return PrintStmt(expression)
    
    # ========================================================================
    # Type Expressions
    # ========================================================================
    
    def simple_type(self, items: List) -> SimpleType:
        """Simple type: Name"""
        name = items[0]
        return SimpleType(name)
    
    def param_type(self, items: List) -> ParamType:
        """Parameterized type: Name<Type>"""
        name = items[0]
        param = items[1]
        return ParamType(name, param)

    def rnd_stream_type(self, items: List) -> RndStreamType:
        """Random stream type: rnd.distribution(args)

        Grammar: RND "." IDENTIFIER "(" arg_list? ")"
        items[0] = "rnd" (RND terminal - ignored)
        items[1] = distribution name (IDENTIFIER)
        items[2] = arguments tuple (from arg_list, if present)
        """
        distribution = items[1]  # e.g., "exponential", "uniform"
        # items[2] contains the arguments from arg_list (which is already a tuple)
        # If arg_list is present, it's items[2]; otherwise only 2 items
        if len(items) > 2:
            # arg_list returns a tuple, so items[2] is the tuple of arguments
            arguments = items[2] if isinstance(items[2], tuple) else (items[2],)
        else:
            arguments = ()
        return RndStreamType(distribution, arguments, stream_name=None)

    def rnd_stream_type_named(self, items: List) -> RndStreamType:
        """Random stream type with explicit name: rnd.distribution(args) as "name"

        Grammar: RND "." IDENTIFIER "(" arg_list? ")" "as" STRING
        items[0] = "rnd" (RND terminal - ignored)
        items[1] = distribution name (IDENTIFIER)
        items[2] = arguments tuple OR stream name string
        items[3] = stream name string (if args present)
        """
        distribution = items[1]  # e.g., "exponential", "uniform"
        # Parse arguments and stream name
        # The STRING token includes quotes, so we need to strip them
        if len(items) == 3:
            # No arguments: rnd.dist() as "name"
            arguments = ()
            stream_name = str(items[2])[1:-1]  # Strip quotes
        else:
            # Has arguments: rnd.dist(args) as "name"
            arguments = items[2] if isinstance(items[2], tuple) else (items[2],)
            stream_name = str(items[3])[1:-1]  # Strip quotes
        return RndStreamType(distribution, arguments, stream_name=stream_name)

    def param_list(self, items: List) -> Tuple[Param, ...]:
        """Parameter list for functions/rules."""
        return tuple(items)
    
    def param(self, items: List) -> Param:
        """Single parameter: name: Type"""
        name = items[0]
        type_expr = items[1]
        return Param(name, type_expr)
    
    # ========================================================================
    # Declarations
    # ========================================================================
    
    def import_decl(self, items: List) -> ImportDecl:
        """Import: import Module as alias"""
        module = items[0]
        alias = items[1]
        return ImportDecl(module, alias)
    
    def domain_simple(self, items: List) -> DomainDecl:
        """Simple domain: domain Name"""
        name = items[0]
        return DomainDecl(name, parent=None)
    
    def domain_extends(self, items: List) -> DomainDecl:
        """Domain with parent: domain Child <: Parent"""
        name = items[0]
        parent = items[1]
        return DomainDecl(name, parent=parent)
    
    def const_decl(self, items: List) -> ConstDecl:
        """Constant: const name: Type"""
        name = items[0]
        type_expr = items[1]
        return ConstDecl(name, type_expr)
    
    def var_decl(self, items: List) -> VarDecl:
        """Variable: var name: Type"""
        name = items[0]
        type_expr = items[1]
        return VarDecl(name, type_expr)
    
    def static_func_decl(self, items: List) -> StaticFuncDecl:
        """Static function: static function name(params): Type"""
        name = items[0]
        if len(items) == 3 and isinstance(items[1], tuple):
            params = items[1]
            return_type = items[2]
        else:
            params = ()
            return_type = items[1]
        return StaticFuncDecl(name, params, return_type)
    
    def dynamic_func_decl(self, items: List) -> DynamicFuncDecl:
        """Dynamic function: dynamic function name(params): Type"""
        name = items[0]
        if len(items) == 3 and isinstance(items[1], tuple):
            params = items[1]
            return_type = items[2]
        else:
            params = ()
            return_type = items[1]
        return DynamicFuncDecl(name, params, return_type)
    
    def derived_func_decl(self, items: List) -> DerivedFuncDecl:
        """Derived function: derived function name(params): Type = expr"""
        name = items[0]
        # Items could be: [name, params, type, expr] or [name, type, expr]
        if len(items) == 4:
            params = items[1]
            return_type = items[2]
            body = items[3]
        else:
            params = ()
            return_type = items[1]
            body = items[2]
        return DerivedFuncDecl(name, params, return_type, body)
    
    def rule_decl(self, items: List) -> RuleDecl:
        """Rule: rule name(params) = body endrule"""
        name = items[0]
        if len(items) == 3 and isinstance(items[1], tuple):
            params = items[1]
            body = items[2]
        else:
            params = ()
            body = items[1]
        return RuleDecl(name, params, body)
    
    def main_rule_decl(self, items: List) -> MainRuleDecl:
        """Main rule: main rule name = body endrule"""
        name = items[0]
        body = items[1]
        return MainRuleDecl(name, body)
    
    def init_block(self, items: List) -> InitBlock:
        """Init block: init: body endinit"""
        body = items[0]
        return InitBlock(body)
    
    # ========================================================================
    # Program
    # ========================================================================
    
    def program(self, items: List) -> Program:
        """Complete program - collect all declarations."""
        prog = Program()
        
        for decl in items:
            if isinstance(decl, ImportDecl):
                prog.imports.append(decl)
            elif isinstance(decl, DomainDecl):
                prog.domains.append(decl)
            elif isinstance(decl, ConstDecl):
                prog.constants.append(decl)
            elif isinstance(decl, VarDecl):
                prog.variables.append(decl)
            elif isinstance(decl, StaticFuncDecl):
                prog.static_funcs.append(decl)
            elif isinstance(decl, DynamicFuncDecl):
                prog.dynamic_funcs.append(decl)
            elif isinstance(decl, DerivedFuncDecl):
                prog.derived_funcs.append(decl)
            elif isinstance(decl, RuleDecl):
                prog.rules.append(decl)
            elif isinstance(decl, MainRuleDecl):
                prog.main_rule = decl
            elif isinstance(decl, InitBlock):
                prog.init = decl
        
        return prog
