"""
experimenter/transformer.py

Lark transformer for experiment and verification specification DSL.

Transforms parse trees into ExperimentNode or VerificationNode AST.
"""

from pathlib import Path
from typing import List, Optional, Any, Dict, Union

from lark import Lark, Transformer, Token, Tree

from .ast import (
    ExperimentNode,
    ReplicationNode,
    StatisticNode,
    ExperimentOutputNode,
    ModelImportNode,
    LabelNode,
    ObservableNode,
    VerificationCheckNode,
    VerificationOutputNode,
    VerificationNode,
)


class ExperimentTransformer(Transformer):
    """
    Transforms Lark parse tree into ExperimentNode or VerificationNode AST.
    
    Usage:
        parser = Lark(grammar, parser='lalr', transformer=ExperimentTransformer())
        result = parser.parse(code)  # Returns ExperimentNode or VerificationNode
    """
    
    # =========================================================================
    # Terminals
    # =========================================================================
    
    def IDENTIFIER(self, token: Token) -> str:
        """Convert identifier token to string."""
        return str(token)
    
    def STRING(self, token: Token) -> str:
        """Convert string token, removing quotes."""
        return str(token)[1:-1]  # Remove surrounding quotes
    
    def INTEGER(self, token: Token) -> int:
        """Convert integer token."""
        return int(token)
    
    def FLOAT(self, token: Token) -> float:
        """Convert float token."""
        return float(token)
    
    def NUMBER(self, token: Token) -> float:
        """Convert number token to float."""
        return float(token)
    
    def BOOL(self, token: Token) -> bool:
        """Convert boolean token."""
        return str(token).lower() == "true"
    
    # =========================================================================
    # Replication Settings (Experiment)
    # =========================================================================
    
    def rep_count(self, children: List[Any]) -> Dict[str, int]:
        """Handle count: N"""
        return {"count": int(children[0])}
    
    def rep_warmup(self, children: List[Any]) -> Dict[str, float]:
        """Handle warm_up_time: N"""
        return {"warm_up_time": float(children[0])}
    
    def rep_length(self, children: List[Any]) -> Dict[str, float]:
        """Handle run_length: N"""
        return {"run_length": float(children[0])}
    
    def rep_strategy(self, children: List[Any]) -> Dict[str, str]:
        """Handle seed_strategy: "strategy" """
        return {"seed_strategy": children[0]}
    
    def rep_base_seed(self, children: List[Any]) -> Dict[str, int]:
        """Handle base_seed: N"""
        return {"base_seed": int(children[0])}
    
    def seed_list(self, children: List[Any]) -> List[int]:
        """Handle [seed1, seed2, ...]"""
        return [int(c) for c in children]
    
    def rep_explicit_seeds(self, children: List[Any]) -> Dict[str, List[int]]:
        """Handle seeds: [list]"""
        return {"explicit_seeds": children[0]}

    def rep_generate_plots(self, children: List[Any]) -> Dict[str, bool]:
        """Handle generate_plots: true/false"""
        return {"generate_plots": children[0]}

    def rep_trace_interval(self, children: List[Any]) -> Dict[str, float]:
        """Handle trace_interval: N"""
        return {"trace_interval": float(children[0])}

    def replication_setting(self, children: List[Any]) -> Dict[str, Any]:
        """Single replication setting."""
        return children[0]
    
    def replication_settings(self, children: List[Any]) -> Dict[str, Any]:
        """Merge all replication settings."""
        result = {}
        for setting in children:
            if isinstance(setting, dict):
                result.update(setting)
        return result
    
    def replication_block(self, children: List[Any]) -> ReplicationNode:
        """Create ReplicationNode from settings."""
        settings = children[0] if children else {}
        return ReplicationNode(
            count=settings.get("count", 30),
            warm_up_time=settings.get("warm_up_time", 0.0),
            run_length=settings.get("run_length", 1000.0),
            seed_strategy=settings.get("seed_strategy", "incremental"),
            base_seed=settings.get("base_seed", 42),
            explicit_seeds=settings.get("explicit_seeds", []),
            generate_plots=settings.get("generate_plots", False),
            trace_interval=settings.get("trace_interval", 1.0),
        )
    
    # =========================================================================
    # Statistics (Experiment)
    # =========================================================================
    
    def stat_expr(self, children: List[Any]) -> Dict[str, str]:
        """Handle expression: "expr" """
        return {"expression": children[0]}
    
    def stat_domain(self, children: List[Any]) -> Dict[str, str]:
        """Handle domain: DomainName"""
        return {"domain": children[0]}
    
    def stat_condition(self, children: List[Any]) -> Dict[str, str]:
        """Handle condition: "cond" """
        return {"condition": children[0]}
    
    def stat_interval(self, children: List[Any]) -> Dict[str, float]:
        """Handle interval: N"""
        return {"interval": float(children[0])}
    
    def stat_aggregation(self, children: List[Any]) -> Dict[str, str]:
        """Handle aggregation: type"""
        return {"aggregation": children[0]}
    
    def stat_start_expr(self, children: List[Any]) -> Dict[str, str]:
        """Handle start_expr: "expr" """
        return {"start_expr": children[0]}
    
    def stat_end_expr(self, children: List[Any]) -> Dict[str, str]:
        """Handle end_expr: "expr" """
        return {"end_expr": children[0]}
    
    def stat_entity_domain(self, children: List[Any]) -> Dict[str, str]:
        """Handle entity_domain: Domain"""
        return {"entity_domain": children[0]}

    def stat_trace(self, children: List[Any]) -> Dict[str, bool]:
        """Handle trace: true/false"""
        return {"trace": children[0]}

    def stat_setting(self, children: List[Any]) -> Dict[str, Any]:
        """Single statistic setting."""
        return children[0]
    
    def stat_body(self, children: List[Any]) -> Dict[str, Any]:
        """Merge all statistic settings."""
        result = {}
        for setting in children:
            if isinstance(setting, dict):
                result.update(setting)
        return result
    
    def statistic_decl(self, children: List[Any]) -> StatisticNode:
        """Create StatisticNode from declaration."""
        name = children[0]
        stat_type = children[1]
        settings = children[2] if len(children) > 2 else {}

        return StatisticNode(
            name=name,
            stat_type=stat_type,
            expression=settings.get("expression"),
            domain=settings.get("domain"),
            condition=settings.get("condition"),
            interval=settings.get("interval"),
            aggregation=settings.get("aggregation", "average"),
            start_expr=settings.get("start_expr"),
            end_expr=settings.get("end_expr"),
            entity_domain=settings.get("entity_domain"),
            trace=settings.get("trace", False),
        )
    
    def statistics_block(self, children: List[Any]) -> List[StatisticNode]:
        """Collect all statistic declarations."""
        return [c for c in children if isinstance(c, StatisticNode)]
    
    # =========================================================================
    # Output (Experiment)
    # =========================================================================
    
    def out_format(self, children: List[Any]) -> Dict[str, str]:
        """Handle format: "json" """
        return {"format": children[0]}
    
    def out_path(self, children: List[Any]) -> Dict[str, str]:
        """Handle file_path: "path" """
        return {"file_path": children[0]}
    
    def output_setting(self, children: List[Any]) -> Dict[str, str]:
        """Single output setting."""
        return children[0]
    
    def output_settings(self, children: List[Any]) -> Dict[str, str]:
        """Merge all output settings."""
        result = {}
        for setting in children:
            if isinstance(setting, dict):
                result.update(setting)
        return result
    
    def output_block(self, children: List[Any]) -> ExperimentOutputNode:
        """Create ExperimentOutputNode from settings."""
        settings = children[0] if children else {}
        return ExperimentOutputNode(
            format=settings.get("format", "json"),
            file_path=settings.get("file_path", "output/results.json"),
        )
    
    # =========================================================================
    # Model and Experiment
    # =========================================================================
    
    def model_decl(self, children: List[Any]) -> str:
        """Handle model := "path" """
        return children[0]
    
    def experiment_body(self, children: List[Any]) -> Dict[str, Any]:
        """Collect experiment body components."""
        result = {
            "model_path": None,
            "replication": ReplicationNode(),
            "statistics": [],
            "output": ExperimentOutputNode(),
        }
        
        for child in children:
            if isinstance(child, str):
                result["model_path"] = child
            elif isinstance(child, ReplicationNode):
                result["replication"] = child
            elif isinstance(child, list) and child and isinstance(child[0], StatisticNode):
                result["statistics"] = child
            elif isinstance(child, ExperimentOutputNode):
                result["output"] = child
        
        return result
    
    def experiment_decl(self, children: List[Any]) -> ExperimentNode:
        """Create ExperimentNode from declaration."""
        name = children[0]
        body = children[1]
        
        return ExperimentNode(
            name=name,
            model_path=body["model_path"],
            replication=body["replication"],
            statistics=body["statistics"],
            output=body["output"],
        )
    
    def experiment_file(self, children: List[Any]) -> ExperimentNode:
        """Return the experiment node."""
        return children[0]
    
    # =========================================================================
    # Verification: Models Block
    # =========================================================================
    
    def model_import_decl(self, children: List[Any]) -> ModelImportNode:
        """Handle import Name from "path" """
        return ModelImportNode(
            name=children[0],
            path=children[1],
        )
    
    def models_block(self, children: List[Any]) -> List[ModelImportNode]:
        """Collect all model imports."""
        return [c for c in children if isinstance(c, ModelImportNode)]
    
    # =========================================================================
    # Verification: Seed Declaration
    # =========================================================================

    def single_seed(self, children: List[Any]) -> List[int]:
        """Handle seed: N (returns list for consistency)"""
        return [int(children[0])]

    def multi_seed(self, children: List[Any]) -> List[int]:
        """Handle seeds: [list]"""
        return children[0]  # seed_list already returns List[int]

    def seed_range(self, children: List[Any]) -> List[int]:
        """Handle seed_range: N to M"""
        start = int(children[0])
        end = int(children[1])
        return list(range(start, end + 1))
    
    # =========================================================================
    # Verification: Labels Block
    # =========================================================================
    
    def label_def(self, children: List[Any]) -> LabelNode:
        """Handle label Name for Model: "predicate" """
        return LabelNode(
            name=children[0],
            model=children[1],
            predicate=children[2],
        )
    
    def labels_block(self, children: List[Any]) -> List[LabelNode]:
        """Collect all label definitions."""
        return [c for c in children if isinstance(c, LabelNode)]
    
    # =========================================================================
    # Verification: Observables Block
    # =========================================================================
    
    def observable_mapping(self, children: List[Any]) -> tuple:
        """Handle model -> label mapping."""
        return (children[0], children[1])
    
    def observable_mappings(self, children: List[Any]) -> Dict[str, str]:
        """Collect all mappings for an observable."""
        return dict(children)
    
    def observable_decl(self, children: List[Any]) -> ObservableNode:
        """Create ObservableNode from declaration."""
        name = children[0]
        mappings = children[1] if len(children) > 1 else {}
        return ObservableNode(name=name, mappings=mappings)
    
    def observables_block(self, children: List[Any]) -> List[ObservableNode]:
        """Collect all observable declarations."""
        return [c for c in children if isinstance(c, ObservableNode)]
    
    # =========================================================================
    # Verification: Check Block
    # =========================================================================
    
    def check_type(self, children: List[Any]) -> Dict[str, str]:
        """Handle type: stutter_equivalence"""
        return {"check_type": children[0]}

    def check_run_length(self, children: List[Any]) -> Dict[str, float]:
        """Handle run_length: N"""
        return {"run_length": float(children[0])}

    def check_timeout(self, children: List[Any]) -> Dict[str, float]:
        """Handle timeout: N"""
        return {"timeout": float(children[0])}

    def check_skip_init(self, children: List[Any]) -> Dict[str, int]:
        """Handle skip_init_steps: N"""
        return {"skip_init_steps": int(children[0])}

    def check_k_max(self, children: List[Any]) -> Dict[str, int]:
        """Handle k_max: N (maximum induction depth for k-induction verification)"""
        return {"k_max": int(children[0])}

    def check_setting(self, children: List[Any]) -> Dict[str, Any]:
        """Single check setting."""
        return children[0]

    def check_settings(self, children: List[Any]) -> Dict[str, Any]:
        """Merge all check settings."""
        result = {}
        for setting in children:
            if isinstance(setting, dict):
                result.update(setting)
        return result

    def check_block(self, children: List[Any]) -> VerificationCheckNode:
        """Create VerificationCheckNode from settings."""
        settings = children[0] if children else {}
        return VerificationCheckNode(
            check_type=settings.get("check_type", "stutter_equivalence"),
            run_length=settings.get("run_length", 10.0),
            timeout=settings.get("timeout"),
            skip_init_steps=settings.get("skip_init_steps", 0),
            k_max=settings.get("k_max"),
        )
    
    # =========================================================================
    # Verification: Output Block
    # =========================================================================
    
    def verify_out_format(self, children: List[Any]) -> Dict[str, str]:
        """Handle format: "json" """
        return {"format": children[0]}
    
    def verify_out_path(self, children: List[Any]) -> Dict[str, str]:
        """Handle file_path: "path" """
        return {"file_path": children[0]}
    
    def verify_out_counterexample(self, children: List[Any]) -> Dict[str, bool]:
        """Handle include_counterexample: true/false"""
        return {"include_counterexample": children[0]}

    def verify_out_generate_plots(self, children: List[Any]) -> Dict[str, bool]:
        """Handle generate_plots: true/false"""
        return {"generate_plots": children[0]}

    def verify_output_setting(self, children: List[Any]) -> Dict[str, Any]:
        """Single verification output setting."""
        return children[0]
    
    def verify_output_settings(self, children: List[Any]) -> Dict[str, Any]:
        """Merge all verification output settings."""
        result = {}
        for setting in children:
            if isinstance(setting, dict):
                result.update(setting)
        return result
    
    def verify_output_block(self, children: List[Any]) -> VerificationOutputNode:
        """Create VerificationOutputNode from settings."""
        settings = children[0] if children else {}
        return VerificationOutputNode(
            format=settings.get("format", "json"),
            file_path=settings.get("file_path", "output/verification_results.json"),
            include_counterexample=settings.get("include_counterexample", True),
            generate_plots=settings.get("generate_plots", False),
        )
    
    # =========================================================================
    # Verification: Main Structure
    # =========================================================================
    
    def verification_body(self, children: List[Any]) -> Dict[str, Any]:
        """Collect verification body components."""
        result = {
            "models": [],
            "seeds": [42],
            "labels": [],
            "observables": [],
            "check": VerificationCheckNode(),
            "output": VerificationOutputNode(),
        }

        for child in children:
            if isinstance(child, list):
                if child and isinstance(child[0], ModelImportNode):
                    result["models"] = child
                elif child and isinstance(child[0], LabelNode):
                    result["labels"] = child
                elif child and isinstance(child[0], ObservableNode):
                    result["observables"] = child
                elif child and isinstance(child[0], int):
                    # List of seeds from single_seed, multi_seed, or seed_range
                    result["seeds"] = child
            elif isinstance(child, VerificationCheckNode):
                result["check"] = child
            elif isinstance(child, VerificationOutputNode):
                result["output"] = child

        return result
    
    def verification_decl(self, children: List[Any]) -> VerificationNode:
        """Create VerificationNode from declaration."""
        name = children[0]
        body = children[1]

        return VerificationNode(
            name=name,
            models=body["models"],
            seeds=body["seeds"],
            labels=body["labels"],
            observables=body["observables"],
            check=body["check"],
            output=body["output"],
        )
    
    def verification_file(self, children: List[Any]) -> VerificationNode:
        """Return the verification node."""
        return children[0]


class ExperimentParser:
    """
    Parser for experiment specification files.
    
    Usage:
        parser = ExperimentParser()
        experiment = parser.parse(code)
        # or
        experiment = parser.parse_file("experiment.simasm")
    """
    
    def __init__(self):
        """Initialize parser with grammar."""
        grammar_path = Path(__file__).parent / "grammar.lark"
        with open(grammar_path) as f:
            grammar = f.read()
        
        self._parser = Lark(
            grammar,
            parser="lalr",
            transformer=ExperimentTransformer(),
            start="experiment_file",
        )
    
    def parse(self, code: str) -> ExperimentNode:
        """
        Parse experiment specification code.
        
        Args:
            code: Experiment specification source code
        
        Returns:
            ExperimentNode AST
        """
        return self._parser.parse(code)
    
    def parse_file(self, path: str) -> ExperimentNode:
        """
        Parse experiment specification from file.

        Args:
            path: Path to .simasm experiment file

        Returns:
            ExperimentNode AST
        """
        with open(path, encoding="utf-8") as f:
            code = f.read()
        return self.parse(code)


class VerificationParser:
    """
    Parser for verification specification files.
    
    Usage:
        parser = VerificationParser()
        verification = parser.parse(code)
        # or
        verification = parser.parse_file("verify.simasm")
    """
    
    def __init__(self):
        """Initialize parser with grammar."""
        grammar_path = Path(__file__).parent / "grammar.lark"
        with open(grammar_path) as f:
            grammar = f.read()
        
        self._parser = Lark(
            grammar,
            parser="lalr",
            transformer=ExperimentTransformer(),
            start="verification_file",
        )
    
    def parse(self, code: str) -> VerificationNode:
        """
        Parse verification specification code.
        
        Args:
            code: Verification specification source code
        
        Returns:
            VerificationNode AST
        """
        return self._parser.parse(code)
    
    def parse_file(self, path: str) -> VerificationNode:
        """
        Parse verification specification from file.

        Args:
            path: Path to .simasm verification file

        Returns:
            VerificationNode AST
        """
        with open(path, encoding="utf-8") as f:
            code = f.read()
        return self.parse(code)


class SpecificationParser:
    """
    Universal parser that auto-detects experiment or verification specs.
    
    Usage:
        parser = SpecificationParser()
        spec = parser.parse(code)  # Returns ExperimentNode or VerificationNode
    """
    
    def __init__(self):
        """Initialize parser with grammar."""
        grammar_path = Path(__file__).parent / "grammar.lark"
        with open(grammar_path) as f:
            grammar = f.read()
        
        self._parser = Lark(
            grammar,
            parser="lalr",
            transformer=ExperimentTransformer(),
        )
    
    def parse(self, code: str) -> Union[ExperimentNode, VerificationNode]:
        """
        Parse specification code, auto-detecting type.
        
        Args:
            code: Specification source code
        
        Returns:
            ExperimentNode or VerificationNode AST
        """
        return self._parser.parse(code)
    
    def parse_file(self, path: str) -> Union[ExperimentNode, VerificationNode]:
        """
        Parse specification from file, auto-detecting type.

        Args:
            path: Path to .simasm specification file

        Returns:
            ExperimentNode or VerificationNode AST
        """
        with open(path, encoding="utf-8") as f:
            code = f.read()
        return self.parse(code)