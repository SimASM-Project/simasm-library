#!/usr/bin/env python3
"""
SimASM HET (Hierarchical Execution Time) Complexity Analyzer

Based on Nowack (2000) "Complexity Theory via Abstract State Machines"
Definition 4.3: Microstep complexity measure

Usage:
    python simasm_het_analyzer.py <file.simasm>
    python simasm_het_analyzer.py warehouse_eg.simasm --verbose
    python simasm_het_analyzer.py warehouse_acd.simasm --json
"""

import re
import sys
import json
import argparse
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum, auto


# =============================================================================
# AST Node Definitions
# =============================================================================

class NodeType(Enum):
    PROGRAM = auto()
    RULE = auto()
    BLOCK = auto()
    UPDATE = auto()
    CONDITIONAL = auto()
    LET_BINDING = auto()
    PAR_BLOCK = auto()
    FUNCTION_CALL = auto()
    VARIABLE = auto()
    CONSTANT = auto()
    BINARY_OP = auto()
    UNARY_OP = auto()
    NEW_ENTITY = auto()
    LIST_LITERAL = auto()
    MEMBER_ACCESS = auto()


@dataclass
class ASTNode:
    node_type: NodeType
    value: str = ""
    children: List['ASTNode'] = field(default_factory=list)
    line_number: int = 0


# =============================================================================
# Lexer
# =============================================================================

class TokenType(Enum):
    # Keywords
    RULE = auto()
    ENDRULE = auto()
    IF = auto()
    THEN = auto()
    ELSE = auto()
    ENDIF = auto()
    LET = auto()
    PAR = auto()
    ENDPAR = auto()
    NEW = auto()
    IMPORT = auto()
    DOMAIN = auto()
    CONST = auto()
    VAR = auto()
    STATIC = auto()
    DYNAMIC = auto()
    FUNCTION = auto()
    AS = auto()
    
    # Operators
    ASSIGN = auto()        # :=
    EQUALS = auto()        # ==
    NOT_EQUALS = auto()    # !=
    LT = auto()            # <
    GT = auto()            # >
    LTE = auto()           # <=
    GTE = auto()           # >=
    PLUS = auto()
    MINUS = auto()
    MULT = auto()
    DIV = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    COLON = auto()
    DOT = auto()
    COMMA = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    SUBTYPE = auto()       # <:
    
    # Literals
    IDENTIFIER = auto()
    NUMBER = auto()
    STRING = auto()
    
    # Other
    NEWLINE = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    column: int


class Lexer:
    KEYWORDS = {
        'rule': TokenType.RULE,
        'endrule': TokenType.ENDRULE,
        'if': TokenType.IF,
        'then': TokenType.THEN,
        'else': TokenType.ELSE,
        'endif': TokenType.ENDIF,
        'let': TokenType.LET,
        'par': TokenType.PAR,
        'endpar': TokenType.ENDPAR,
        'new': TokenType.NEW,
        'import': TokenType.IMPORT,
        'domain': TokenType.DOMAIN,
        'const': TokenType.CONST,
        'var': TokenType.VAR,
        'static': TokenType.STATIC,
        'dynamic': TokenType.DYNAMIC,
        'function': TokenType.FUNCTION,
        'as': TokenType.AS,
        'and': TokenType.AND,
        'or': TokenType.OR,
        'not': TokenType.NOT,
    }
    
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []
    
    def current_char(self) -> Optional[str]:
        if self.pos >= len(self.source):
            return None
        return self.source[self.pos]
    
    def peek_char(self, offset: int = 1) -> Optional[str]:
        pos = self.pos + offset
        if pos >= len(self.source):
            return None
        return self.source[pos]
    
    def advance(self) -> str:
        char = self.current_char()
        self.pos += 1
        if char == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char
    
    def skip_whitespace_and_comments(self):
        while self.current_char():
            # Skip whitespace (but not newlines for statement separation)
            if self.current_char() in ' \t\r':
                self.advance()
            # Skip single-line comments
            elif self.current_char() == '/' and self.peek_char() == '/':
                while self.current_char() and self.current_char() != '\n':
                    self.advance()
            # Skip multi-line comments
            elif self.current_char() == '/' and self.peek_char() == '*':
                self.advance()  # /
                self.advance()  # *
                while self.current_char():
                    if self.current_char() == '*' and self.peek_char() == '/':
                        self.advance()  # *
                        self.advance()  # /
                        break
                    self.advance()
            else:
                break
    
    def read_string(self) -> str:
        quote = self.advance()  # consume opening quote
        value = ""
        while self.current_char() and self.current_char() != quote:
            if self.current_char() == '\\':
                self.advance()
                if self.current_char():
                    value += self.advance()
            else:
                value += self.advance()
        if self.current_char() == quote:
            self.advance()  # consume closing quote
        return value
    
    def read_number(self) -> str:
        value = ""
        while self.current_char() and (self.current_char().isdigit() or self.current_char() == '.'):
            value += self.advance()
        return value
    
    def read_identifier(self) -> str:
        value = ""
        while self.current_char() and (self.current_char().isalnum() or self.current_char() == '_'):
            value += self.advance()
        return value
    
    def tokenize(self) -> List[Token]:
        while self.current_char():
            self.skip_whitespace_and_comments()
            
            if not self.current_char():
                break
            
            line, col = self.line, self.column
            char = self.current_char()
            
            # Newline
            if char == '\n':
                self.advance()
                self.tokens.append(Token(TokenType.NEWLINE, '\n', line, col))
            
            # String literals
            elif char in '"\'':
                value = self.read_string()
                self.tokens.append(Token(TokenType.STRING, value, line, col))
            
            # Numbers
            elif char.isdigit():
                value = self.read_number()
                self.tokens.append(Token(TokenType.NUMBER, value, line, col))
            
            # Identifiers and keywords
            elif char.isalpha() or char == '_':
                value = self.read_identifier()
                # Case-sensitive keyword matching (lowercase only)
                token_type = self.KEYWORDS.get(value, TokenType.IDENTIFIER)
                self.tokens.append(Token(token_type, value, line, col))
            
            # Two-character operators
            elif char == ':' and self.peek_char() == '=':
                self.advance()
                self.advance()
                self.tokens.append(Token(TokenType.ASSIGN, ':=', line, col))
            elif char == '=' and self.peek_char() == '=':
                self.advance()
                self.advance()
                self.tokens.append(Token(TokenType.EQUALS, '==', line, col))
            elif char == '!' and self.peek_char() == '=':
                self.advance()
                self.advance()
                self.tokens.append(Token(TokenType.NOT_EQUALS, '!=', line, col))
            elif char == '<' and self.peek_char() == '=':
                self.advance()
                self.advance()
                self.tokens.append(Token(TokenType.LTE, '<=', line, col))
            elif char == '>' and self.peek_char() == '=':
                self.advance()
                self.advance()
                self.tokens.append(Token(TokenType.GTE, '>=', line, col))
            elif char == '<' and self.peek_char() == ':':
                self.advance()
                self.advance()
                self.tokens.append(Token(TokenType.SUBTYPE, '<:', line, col))
            
            # Single-character operators
            elif char == '<':
                self.advance()
                self.tokens.append(Token(TokenType.LT, '<', line, col))
            elif char == '>':
                self.advance()
                self.tokens.append(Token(TokenType.GT, '>', line, col))
            elif char == '+':
                self.advance()
                self.tokens.append(Token(TokenType.PLUS, '+', line, col))
            elif char == '-':
                self.advance()
                self.tokens.append(Token(TokenType.MINUS, '-', line, col))
            elif char == '*':
                self.advance()
                self.tokens.append(Token(TokenType.MULT, '*', line, col))
            elif char == '/':
                self.advance()
                self.tokens.append(Token(TokenType.DIV, '/', line, col))
            elif char == ':':
                self.advance()
                self.tokens.append(Token(TokenType.COLON, ':', line, col))
            elif char == '.':
                self.advance()
                self.tokens.append(Token(TokenType.DOT, '.', line, col))
            elif char == ',':
                self.advance()
                self.tokens.append(Token(TokenType.COMMA, ',', line, col))
            elif char == '(':
                self.advance()
                self.tokens.append(Token(TokenType.LPAREN, '(', line, col))
            elif char == ')':
                self.advance()
                self.tokens.append(Token(TokenType.RPAREN, ')', line, col))
            elif char == '[':
                self.advance()
                self.tokens.append(Token(TokenType.LBRACKET, '[', line, col))
            elif char == ']':
                self.advance()
                self.tokens.append(Token(TokenType.RBRACKET, ']', line, col))
            elif char == '=':
                self.advance()
                # Single = used in rule definitions
                self.tokens.append(Token(TokenType.EQUALS, '=', line, col))
            else:
                # Skip unknown characters
                self.advance()
        
        self.tokens.append(Token(TokenType.EOF, '', self.line, self.column))
        return self.tokens


# =============================================================================
# Parser
# =============================================================================

class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = [t for t in tokens if t.type != TokenType.NEWLINE]
        self.pos = 0
        self.rules: List[ASTNode] = []
    
    def current_token(self) -> Token:
        if self.pos >= len(self.tokens):
            return self.tokens[-1]  # EOF
        return self.tokens[self.pos]
    
    def peek_token(self, offset: int = 1) -> Token:
        pos = self.pos + offset
        if pos >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[pos]
    
    def advance(self) -> Token:
        token = self.current_token()
        self.pos += 1
        return token
    
    def expect(self, token_type: TokenType) -> Token:
        token = self.current_token()
        if token.type != token_type:
            raise SyntaxError(f"Expected {token_type}, got {token.type} at line {token.line}")
        return self.advance()
    
    def match(self, *token_types: TokenType) -> bool:
        return self.current_token().type in token_types
    
    def parse(self) -> ASTNode:
        """Parse the entire program and extract rules."""
        program = ASTNode(NodeType.PROGRAM, "program")
        
        while not self.match(TokenType.EOF):
            if self.match(TokenType.RULE):
                rule = self.parse_rule()
                program.children.append(rule)
                self.rules.append(rule)
            else:
                # Skip any non-rule content (declarations, comments, etc.)
                self.skip_declaration()
        
        return program
    
    def skip_declaration(self):
        """Skip over a declaration until the next rule or EOF."""
        # Just advance one token at a time
        # The main parse loop will catch rules
        if not self.match(TokenType.RULE, TokenType.EOF):
            self.advance()
    
    def parse_rule(self) -> ASTNode:
        """Parse a rule definition."""
        self.expect(TokenType.RULE)
        
        name_token = self.expect(TokenType.IDENTIFIER)
        rule_name = name_token.value
        
        # Parse parameters
        params = []
        if self.match(TokenType.LPAREN):
            self.advance()
            while not self.match(TokenType.RPAREN):
                if self.match(TokenType.IDENTIFIER):
                    param_name = self.advance().value
                    # Skip type annotation
                    if self.match(TokenType.COLON):
                        self.advance()
                        self.parse_type()
                    params.append(param_name)
                if self.match(TokenType.COMMA):
                    self.advance()
            self.expect(TokenType.RPAREN)
        
        # Skip = sign
        if self.match(TokenType.EQUALS):
            self.advance()
        
        # Parse rule body
        body = self.parse_statement_list()
        
        # Expect endrule
        if self.match(TokenType.ENDRULE):
            self.advance()
        
        rule_node = ASTNode(NodeType.RULE, rule_name, [body], name_token.line)
        return rule_node
    
    def parse_type(self):
        """Skip type annotations."""
        # Handle generic types like List<Event>
        if self.match(TokenType.IDENTIFIER):
            self.advance()
            if self.match(TokenType.LT):
                self.advance()
                self.parse_type()
                if self.match(TokenType.GT):
                    self.advance()
    
    def parse_statement_list(self) -> ASTNode:
        """Parse a sequence of statements (implicit block)."""
        statements = []
        
        while not self.match(TokenType.ENDRULE, TokenType.ENDIF, TokenType.ELSE, 
                            TokenType.ENDPAR, TokenType.EOF):
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
        
        if len(statements) == 1:
            return statements[0]
        
        return ASTNode(NodeType.BLOCK, "block", statements)
    
    def parse_statement(self) -> Optional[ASTNode]:
        """Parse a single statement."""
        token = self.current_token()
        
        if self.match(TokenType.IF):
            return self.parse_if()
        elif self.match(TokenType.LET):
            return self.parse_let()
        elif self.match(TokenType.PAR):
            return self.parse_par()
        elif self.match(TokenType.IDENTIFIER):
            return self.parse_assignment_or_call()
        else:
            # Skip unknown tokens
            self.advance()
            return None
    
    def parse_if(self) -> ASTNode:
        """Parse if-then-else statement."""
        line = self.current_token().line
        self.expect(TokenType.IF)
        
        condition = self.parse_expression()
        
        self.expect(TokenType.THEN)
        
        then_branch = self.parse_statement_list()
        
        else_branch = None
        if self.match(TokenType.ELSE):
            self.advance()
            else_branch = self.parse_statement_list()
        
        self.expect(TokenType.ENDIF)
        
        children = [condition, then_branch]
        if else_branch:
            children.append(else_branch)
        
        return ASTNode(NodeType.CONDITIONAL, "if", children, line)
    
    def parse_let(self) -> ASTNode:
        """Parse let binding."""
        line = self.current_token().line
        self.expect(TokenType.LET)
        
        var_name = self.expect(TokenType.IDENTIFIER).value
        
        self.expect(TokenType.EQUALS)
        
        expr = self.parse_expression()
        
        # In SimASM, let bindings are followed by more statements
        # We'll treat subsequent statements as the "body"
        var_node = ASTNode(NodeType.VARIABLE, var_name, [], line)
        
        return ASTNode(NodeType.LET_BINDING, var_name, [expr], line)
    
    def parse_par(self) -> ASTNode:
        """Parse parallel block."""
        line = self.current_token().line
        self.expect(TokenType.PAR)
        
        statements = []
        while not self.match(TokenType.ENDPAR, TokenType.EOF):
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
        
        self.expect(TokenType.ENDPAR)
        
        return ASTNode(NodeType.PAR_BLOCK, "par", statements, line)
    
    def parse_assignment_or_call(self) -> ASTNode:
        """Parse assignment or function call."""
        line = self.current_token().line
        
        # Parse the left side (could be simple var, function app, or member access)
        left = self.parse_primary()
        
        # Check for assignment
        if self.match(TokenType.ASSIGN):
            self.advance()
            right = self.parse_expression()
            return ASTNode(NodeType.UPDATE, ":=", [left, right], line)
        
        # Otherwise it's a standalone expression (function call)
        return left
    
    def parse_expression(self) -> ASTNode:
        """Parse an expression with operator precedence."""
        return self.parse_or()
    
    def parse_or(self) -> ASTNode:
        left = self.parse_and()
        
        while self.match(TokenType.OR):
            op = self.advance().value
            right = self.parse_and()
            left = ASTNode(NodeType.BINARY_OP, op, [left, right])
        
        return left
    
    def parse_and(self) -> ASTNode:
        left = self.parse_comparison()
        
        while self.match(TokenType.AND):
            op = self.advance().value
            right = self.parse_comparison()
            left = ASTNode(NodeType.BINARY_OP, op, [left, right])
        
        return left
    
    def parse_comparison(self) -> ASTNode:
        left = self.parse_additive()
        
        while self.match(TokenType.LT, TokenType.GT, TokenType.LTE, TokenType.GTE,
                        TokenType.EQUALS, TokenType.NOT_EQUALS):
            op = self.advance().value
            right = self.parse_additive()
            left = ASTNode(NodeType.BINARY_OP, op, [left, right])
        
        return left
    
    def parse_additive(self) -> ASTNode:
        left = self.parse_multiplicative()
        
        while self.match(TokenType.PLUS, TokenType.MINUS):
            op = self.advance().value
            right = self.parse_multiplicative()
            left = ASTNode(NodeType.BINARY_OP, op, [left, right])
        
        return left
    
    def parse_multiplicative(self) -> ASTNode:
        left = self.parse_unary()
        
        while self.match(TokenType.MULT, TokenType.DIV):
            op = self.advance().value
            right = self.parse_unary()
            left = ASTNode(NodeType.BINARY_OP, op, [left, right])
        
        return left
    
    def parse_unary(self) -> ASTNode:
        if self.match(TokenType.NOT, TokenType.MINUS):
            op = self.advance().value
            operand = self.parse_unary()
            return ASTNode(NodeType.UNARY_OP, op, [operand])
        
        return self.parse_primary()
    
    def parse_primary(self) -> ASTNode:
        """Parse primary expression."""
        token = self.current_token()
        line = token.line
        
        # Number literal
        if self.match(TokenType.NUMBER):
            self.advance()
            return ASTNode(NodeType.CONSTANT, token.value, [], line)
        
        # String literal
        if self.match(TokenType.STRING):
            self.advance()
            return ASTNode(NodeType.CONSTANT, f'"{token.value}"', [], line)
        
        # new Entity
        if self.match(TokenType.NEW):
            self.advance()
            type_name = self.expect(TokenType.IDENTIFIER).value
            return ASTNode(NodeType.NEW_ENTITY, type_name, [], line)
        
        # List literal []
        if self.match(TokenType.LBRACKET):
            self.advance()
            elements = []
            while not self.match(TokenType.RBRACKET, TokenType.EOF):
                elements.append(self.parse_expression())
                if self.match(TokenType.COMMA):
                    self.advance()
            self.expect(TokenType.RBRACKET)
            return ASTNode(NodeType.LIST_LITERAL, "[]", elements, line)
        
        # Parenthesized expression
        if self.match(TokenType.LPAREN):
            self.advance()
            expr = self.parse_expression()
            self.expect(TokenType.RPAREN)
            return expr
        
        # Identifier (variable, function call, or member access)
        if self.match(TokenType.IDENTIFIER):
            name = self.advance().value
            
            # Check for member access (e.g., lib.add)
            while self.match(TokenType.DOT):
                self.advance()
                member = self.expect(TokenType.IDENTIFIER).value
                name = f"{name}.{member}"
            
            # Check for function call
            if self.match(TokenType.LPAREN):
                self.advance()
                args = []
                while not self.match(TokenType.RPAREN, TokenType.EOF):
                    args.append(self.parse_expression())
                    if self.match(TokenType.COMMA):
                        self.advance()
                self.expect(TokenType.RPAREN)
                return ASTNode(NodeType.FUNCTION_CALL, name, args, line)
            
            return ASTNode(NodeType.VARIABLE, name, [], line)
        
        # Unknown - return empty node
        self.advance()
        return ASTNode(NodeType.CONSTANT, "unknown", [], line)


# =============================================================================
# HET Calculator
# =============================================================================

@dataclass
class HETResult:
    """Result of HET calculation for a node."""
    het: int
    updates: int
    conditionals: int
    let_bindings: int
    function_calls: int
    new_entities: int
    list_operations: int
    variables: int
    constants: int


class HETCalculator:
    """
    Calculate HET (Hierarchical Execution Time) based on Nowack (2000).
    
    HET measures the number of microsteps required to execute an ASM rule.
    """
    
    # Cost constants (can be calibrated)
    COST_VAR = 1          # Variable access
    COST_CONST = 1        # Constant
    COST_FUNC_BASE = 1    # Function application base cost
    COST_UPDATE_BASE = 1  # Update base cost
    COST_BLOCK_BASE = 1   # Block base cost
    COST_COND_BASE = 1    # Conditional base cost
    COST_LET_BASE = 1     # Let binding base cost
    COST_PAR_BASE = 1     # Parallel block base cost
    COST_NEW = 3          # Entity creation cost
    COST_LIST_OP = 2      # List operation cost
    COST_BINARY_OP = 1    # Binary operator cost
    COST_UNARY_OP = 1     # Unary operator cost
    
    def calculate(self, node: ASTNode) -> HETResult:
        """Calculate HET for an AST node."""
        if node.node_type == NodeType.VARIABLE:
            return HETResult(
                het=self.COST_VAR,
                updates=0, conditionals=0, let_bindings=0,
                function_calls=0, new_entities=0, list_operations=0,
                variables=1, constants=0
            )
        
        elif node.node_type == NodeType.CONSTANT:
            return HETResult(
                het=self.COST_CONST,
                updates=0, conditionals=0, let_bindings=0,
                function_calls=0, new_entities=0, list_operations=0,
                variables=0, constants=1
            )
        
        elif node.node_type == NodeType.FUNCTION_CALL:
            # HET = 1 + sum(HET(args))
            args_het = sum(self.calculate(arg).het for arg in node.children)
            args_results = [self.calculate(arg) for arg in node.children]
            
            # Check if it's a list operation
            is_list_op = node.value.startswith('lib.') or node.value in ['add', 'remove', 'pop', 'get', 'first', 'length']
            
            return HETResult(
                het=self.COST_FUNC_BASE + args_het + (self.COST_LIST_OP if is_list_op else 0),
                updates=sum(r.updates for r in args_results),
                conditionals=sum(r.conditionals for r in args_results),
                let_bindings=sum(r.let_bindings for r in args_results),
                function_calls=1 + sum(r.function_calls for r in args_results),
                new_entities=sum(r.new_entities for r in args_results),
                list_operations=(1 if is_list_op else 0) + sum(r.list_operations for r in args_results),
                variables=sum(r.variables for r in args_results),
                constants=sum(r.constants for r in args_results)
            )
        
        elif node.node_type == NodeType.UPDATE:
            # HET = 1 + HET(location) + HET(value)
            loc_result = self.calculate(node.children[0])
            val_result = self.calculate(node.children[1])
            
            return HETResult(
                het=self.COST_UPDATE_BASE + loc_result.het + val_result.het,
                updates=1 + loc_result.updates + val_result.updates,
                conditionals=loc_result.conditionals + val_result.conditionals,
                let_bindings=loc_result.let_bindings + val_result.let_bindings,
                function_calls=loc_result.function_calls + val_result.function_calls,
                new_entities=loc_result.new_entities + val_result.new_entities,
                list_operations=loc_result.list_operations + val_result.list_operations,
                variables=loc_result.variables + val_result.variables,
                constants=loc_result.constants + val_result.constants
            )
        
        elif node.node_type == NodeType.BLOCK:
            # HET = 1 + sum(HET(statements))
            results = [self.calculate(stmt) for stmt in node.children]
            
            return HETResult(
                het=self.COST_BLOCK_BASE + sum(r.het for r in results),
                updates=sum(r.updates for r in results),
                conditionals=sum(r.conditionals for r in results),
                let_bindings=sum(r.let_bindings for r in results),
                function_calls=sum(r.function_calls for r in results),
                new_entities=sum(r.new_entities for r in results),
                list_operations=sum(r.list_operations for r in results),
                variables=sum(r.variables for r in results),
                constants=sum(r.constants for r in results)
            )
        
        elif node.node_type == NodeType.CONDITIONAL:
            # HET = 1 + HET(guard) + HET(then) [+ HET(else)]
            guard_result = self.calculate(node.children[0])
            then_result = self.calculate(node.children[1])
            else_result = self.calculate(node.children[2]) if len(node.children) > 2 else HETResult(0,0,0,0,0,0,0,0,0)
            
            return HETResult(
                het=self.COST_COND_BASE + guard_result.het + then_result.het + else_result.het,
                updates=guard_result.updates + then_result.updates + else_result.updates,
                conditionals=1 + guard_result.conditionals + then_result.conditionals + else_result.conditionals,
                let_bindings=guard_result.let_bindings + then_result.let_bindings + else_result.let_bindings,
                function_calls=guard_result.function_calls + then_result.function_calls + else_result.function_calls,
                new_entities=guard_result.new_entities + then_result.new_entities + else_result.new_entities,
                list_operations=guard_result.list_operations + then_result.list_operations + else_result.list_operations,
                variables=guard_result.variables + then_result.variables + else_result.variables,
                constants=guard_result.constants + then_result.constants + else_result.constants
            )
        
        elif node.node_type == NodeType.LET_BINDING:
            # HET = 1 + HET(expr)
            expr_result = self.calculate(node.children[0]) if node.children else HETResult(0,0,0,0,0,0,0,0,0)
            
            return HETResult(
                het=self.COST_LET_BASE + expr_result.het,
                updates=expr_result.updates,
                conditionals=expr_result.conditionals,
                let_bindings=1 + expr_result.let_bindings,
                function_calls=expr_result.function_calls,
                new_entities=expr_result.new_entities,
                list_operations=expr_result.list_operations,
                variables=expr_result.variables,
                constants=expr_result.constants
            )
        
        elif node.node_type == NodeType.PAR_BLOCK:
            # HET = 1 + sum(HET(rules))
            results = [self.calculate(stmt) for stmt in node.children]
            
            return HETResult(
                het=self.COST_PAR_BASE + sum(r.het for r in results),
                updates=sum(r.updates for r in results),
                conditionals=sum(r.conditionals for r in results),
                let_bindings=sum(r.let_bindings for r in results),
                function_calls=sum(r.function_calls for r in results),
                new_entities=sum(r.new_entities for r in results),
                list_operations=sum(r.list_operations for r in results),
                variables=sum(r.variables for r in results),
                constants=sum(r.constants for r in results)
            )
        
        elif node.node_type == NodeType.NEW_ENTITY:
            return HETResult(
                het=self.COST_NEW,
                updates=0, conditionals=0, let_bindings=0,
                function_calls=0, new_entities=1, list_operations=0,
                variables=0, constants=0
            )
        
        elif node.node_type == NodeType.LIST_LITERAL:
            results = [self.calculate(elem) for elem in node.children]
            
            return HETResult(
                het=1 + sum(r.het for r in results),
                updates=sum(r.updates for r in results),
                conditionals=sum(r.conditionals for r in results),
                let_bindings=sum(r.let_bindings for r in results),
                function_calls=sum(r.function_calls for r in results),
                new_entities=sum(r.new_entities for r in results),
                list_operations=sum(r.list_operations for r in results),
                variables=sum(r.variables for r in results),
                constants=sum(r.constants for r in results)
            )
        
        elif node.node_type == NodeType.BINARY_OP:
            left_result = self.calculate(node.children[0])
            right_result = self.calculate(node.children[1])
            
            return HETResult(
                het=self.COST_BINARY_OP + left_result.het + right_result.het,
                updates=left_result.updates + right_result.updates,
                conditionals=left_result.conditionals + right_result.conditionals,
                let_bindings=left_result.let_bindings + right_result.let_bindings,
                function_calls=left_result.function_calls + right_result.function_calls,
                new_entities=left_result.new_entities + right_result.new_entities,
                list_operations=left_result.list_operations + right_result.list_operations,
                variables=left_result.variables + right_result.variables,
                constants=left_result.constants + right_result.constants
            )
        
        elif node.node_type == NodeType.UNARY_OP:
            operand_result = self.calculate(node.children[0])
            
            return HETResult(
                het=self.COST_UNARY_OP + operand_result.het,
                updates=operand_result.updates,
                conditionals=operand_result.conditionals,
                let_bindings=operand_result.let_bindings,
                function_calls=operand_result.function_calls,
                new_entities=operand_result.new_entities,
                list_operations=operand_result.list_operations,
                variables=operand_result.variables,
                constants=operand_result.constants
            )
        
        elif node.node_type == NodeType.RULE:
            # Rule HET = HET(body)
            if node.children:
                return self.calculate(node.children[0])
            return HETResult(0,0,0,0,0,0,0,0,0)
        
        elif node.node_type == NodeType.PROGRAM:
            results = [self.calculate(rule) for rule in node.children]
            
            return HETResult(
                het=sum(r.het for r in results),
                updates=sum(r.updates for r in results),
                conditionals=sum(r.conditionals for r in results),
                let_bindings=sum(r.let_bindings for r in results),
                function_calls=sum(r.function_calls for r in results),
                new_entities=sum(r.new_entities for r in results),
                list_operations=sum(r.list_operations for r in results),
                variables=sum(r.variables for r in results),
                constants=sum(r.constants for r in results)
            )
        
        # Default
        return HETResult(0,0,0,0,0,0,0,0,0)


# =============================================================================
# Analyzer
# =============================================================================

@dataclass
class RuleAnalysis:
    name: str
    line: int
    het: int
    updates: int
    conditionals: int
    let_bindings: int
    function_calls: int
    new_entities: int
    list_operations: int


@dataclass
class ProgramAnalysis:
    filename: str
    total_rules: int
    total_het: int
    avg_het: float
    state_update_density: float
    rules: List[RuleAnalysis]
    
    # Aggregate counts
    total_updates: int
    total_conditionals: int
    total_let_bindings: int
    total_function_calls: int
    total_new_entities: int
    total_list_operations: int


def analyze_simasm(source: str, filename: str = "input.simasm") -> ProgramAnalysis:
    """Analyze a SimASM source file and compute HET complexity."""
    
    # Lexical analysis
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    
    # Parsing
    parser = Parser(tokens)
    program_ast = parser.parse()
    
    # HET calculation
    calculator = HETCalculator()
    
    rule_analyses = []
    total_het = 0
    total_updates = 0
    total_conditionals = 0
    total_let_bindings = 0
    total_function_calls = 0
    total_new_entities = 0
    total_list_operations = 0
    
    for rule_node in parser.rules:
        result = calculator.calculate(rule_node)
        
        analysis = RuleAnalysis(
            name=rule_node.value,
            line=rule_node.line_number,
            het=result.het,
            updates=result.updates,
            conditionals=result.conditionals,
            let_bindings=result.let_bindings,
            function_calls=result.function_calls,
            new_entities=result.new_entities,
            list_operations=result.list_operations
        )
        rule_analyses.append(analysis)
        
        total_het += result.het
        total_updates += result.updates
        total_conditionals += result.conditionals
        total_let_bindings += result.let_bindings
        total_function_calls += result.function_calls
        total_new_entities += result.new_entities
        total_list_operations += result.list_operations
    
    num_rules = len(rule_analyses)
    avg_het = total_het / num_rules if num_rules > 0 else 0
    sud = total_updates / num_rules if num_rules > 0 else 0
    
    return ProgramAnalysis(
        filename=filename,
        total_rules=num_rules,
        total_het=total_het,
        avg_het=avg_het,
        state_update_density=sud,
        rules=rule_analyses,
        total_updates=total_updates,
        total_conditionals=total_conditionals,
        total_let_bindings=total_let_bindings,
        total_function_calls=total_function_calls,
        total_new_entities=total_new_entities,
        total_list_operations=total_list_operations
    )


def print_analysis(analysis: ProgramAnalysis, verbose: bool = False):
    """Print analysis results in human-readable format."""
    
    print("=" * 70)
    print(f"SimASM HET Complexity Analysis: {analysis.filename}")
    print("=" * 70)
    print()
    
    print("SUMMARY")
    print("-" * 40)
    print(f"  Total Rules:              {analysis.total_rules}")
    print(f"  Total HET (microsteps):   {analysis.total_het}")
    print(f"  Average HET per Rule:     {analysis.avg_het:.2f}")
    print(f"  State Update Density:     {analysis.state_update_density:.2f}")
    print()
    
    print("AGGREGATE METRICS")
    print("-" * 40)
    print(f"  Total Updates:            {analysis.total_updates}")
    print(f"  Total Conditionals:       {analysis.total_conditionals}")
    print(f"  Total Let Bindings:       {analysis.total_let_bindings}")
    print(f"  Total Function Calls:     {analysis.total_function_calls}")
    print(f"  Total New Entities:       {analysis.total_new_entities}")
    print(f"  Total List Operations:    {analysis.total_list_operations}")
    print()
    
    if verbose:
        print("RULE-BY-RULE ANALYSIS")
        print("-" * 70)
        print(f"{'Rule Name':<35} {'Line':>6} {'HET':>8} {'Upd':>5} {'Cond':>5} {'Let':>5}")
        print("-" * 70)
        
        # Sort by HET descending
        sorted_rules = sorted(analysis.rules, key=lambda r: r.het, reverse=True)
        
        for rule in sorted_rules:
            name = rule.name[:34] if len(rule.name) > 34 else rule.name
            print(f"{name:<35} {rule.line:>6} {rule.het:>8} {rule.updates:>5} {rule.conditionals:>5} {rule.let_bindings:>5}")
        
        print("-" * 70)
    
    print()
    print("TOP 10 MOST COMPLEX RULES")
    print("-" * 50)
    sorted_rules = sorted(analysis.rules, key=lambda r: r.het, reverse=True)[:10]
    for i, rule in enumerate(sorted_rules, 1):
        print(f"  {i:2}. {rule.name:<35} HET: {rule.het}")
    
    print()


def analysis_to_dict(analysis: ProgramAnalysis) -> dict:
    """Convert analysis to dictionary for JSON output."""
    return {
        "filename": analysis.filename,
        "summary": {
            "total_rules": analysis.total_rules,
            "total_het": analysis.total_het,
            "avg_het": round(analysis.avg_het, 2),
            "state_update_density": round(analysis.state_update_density, 2)
        },
        "aggregate_metrics": {
            "total_updates": analysis.total_updates,
            "total_conditionals": analysis.total_conditionals,
            "total_let_bindings": analysis.total_let_bindings,
            "total_function_calls": analysis.total_function_calls,
            "total_new_entities": analysis.total_new_entities,
            "total_list_operations": analysis.total_list_operations
        },
        "rules": [
            {
                "name": r.name,
                "line": r.line,
                "het": r.het,
                "updates": r.updates,
                "conditionals": r.conditionals,
                "let_bindings": r.let_bindings,
                "function_calls": r.function_calls,
                "new_entities": r.new_entities,
                "list_operations": r.list_operations
            }
            for r in sorted(analysis.rules, key=lambda x: x.het, reverse=True)
        ]
    }


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="SimASM HET Complexity Analyzer - Based on Nowack (2000)"
    )
    parser.add_argument("file", help="SimASM file to analyze (.simasm)")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Show detailed rule-by-rule analysis")
    parser.add_argument("--json", action="store_true",
                       help="Output results as JSON")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    
    args = parser.parse_args()
    
    # Read input file
    try:
        with open(args.file, 'r') as f:
            source = f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Analyze
    try:
        analysis = analyze_simasm(source, args.file)
    except Exception as e:
        print(f"Error analyzing file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Output
    if args.json:
        output = json.dumps(analysis_to_dict(analysis), indent=2)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
        else:
            print(output)
    else:
        if args.output:
            import io
            import contextlib
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                print_analysis(analysis, args.verbose)
            with open(args.output, 'w') as out:
                out.write(f.getvalue())
        else:
            print_analysis(analysis, args.verbose)


if __name__ == "__main__":
    main()
