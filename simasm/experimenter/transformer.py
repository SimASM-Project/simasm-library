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
    TimeseriesObservableNode,
    TimeseriesPlotConfigNode,
    VerificationCheckNode,
    VerificationOutputNode,
    VerificationNode,
    AnalysisModelNode,
    AnalysisMetricsNode,
    AnalysisRuntimeNode,
    AnalysisRegressionNode,
    AnalysisOutputNode,
    AnalysisNode,
    ComplexityModelNode,
    ComplexityMetricsNode,
    ComplexityOutputNode,
    ComplexityNode,
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
    # Verification: Timeseries Block
    # =========================================================================

    def timeseries_observe(self, children: List[Any]) -> TimeseriesObservableNode:
        """Handle observe Name for Model: "expression" """
        return TimeseriesObservableNode(
            name=children[0],
            model=children[1],
            expression=children[2],
        )

    def timeseries_block(self, children: List[Any]) -> List[TimeseriesObservableNode]:
        """Collect all timeseries observable definitions."""
        return [c for c in children if isinstance(c, TimeseriesObservableNode)]

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

    def timeseries_layout(self, children: List[Any]) -> tuple:
        """Handle [rows, cols] layout."""
        return (int(children[0]), int(children[1]))

    def ts_plot_layout(self, children: List[Any]) -> Dict[str, tuple]:
        """Handle layout: [rows, cols]"""
        return {"layout": children[0]}

    def ts_plot_observable(self, children: List[Any]) -> Dict[str, str]:
        """Handle observable: name"""
        return {"observable": children[0]}

    def ts_plot_y_label(self, children: List[Any]) -> Dict[str, str]:
        """Handle y_label: "label" """
        return {"y_label": children[0]}

    def ts_plot_y_min(self, children: List[Any]) -> Dict[str, float]:
        """Handle y_min: N"""
        return {"y_min": float(children[0])}

    def ts_plot_y_max(self, children: List[Any]) -> Dict[str, float]:
        """Handle y_max: N"""
        return {"y_max": float(children[0])}

    def ts_plot_show_raw(self, children: List[Any]) -> Dict[str, bool]:
        """Handle show_raw: true/false"""
        return {"show_raw": children[0]}

    def ts_plot_show_no_stutter(self, children: List[Any]) -> Dict[str, bool]:
        """Handle show_no_stutter: true/false"""
        return {"show_no_stutter": children[0]}

    def ts_plot_output_file(self, children: List[Any]) -> Dict[str, str]:
        """Handle output_file: "filename" """
        return {"output_file": children[0]}

    def timeseries_plot_setting(self, children: List[Any]) -> Dict[str, Any]:
        """Single timeseries plot setting."""
        return children[0]

    def timeseries_plot_settings(self, children: List[Any]) -> Dict[str, Any]:
        """Merge all timeseries plot settings."""
        result = {}
        for setting in children:
            if isinstance(setting, dict):
                result.update(setting)
        return result

    def verify_out_timeseries(self, children: List[Any]) -> Dict[str, TimeseriesPlotConfigNode]:
        """Handle timeseries_plots: ... endtimeseries_plots"""
        settings = children[0] if children else {}
        config = TimeseriesPlotConfigNode(
            layout=settings.get("layout", (6, 2)),
            observable=settings.get("observable", ""),
            y_label=settings.get("y_label", "Value"),
            y_min=settings.get("y_min"),
            y_max=settings.get("y_max"),
            show_raw=settings.get("show_raw", True),
            show_no_stutter=settings.get("show_no_stutter", True),
            output_file=settings.get("output_file", "timeseries_traces.png"),
        )
        return {"timeseries_plot_config": config}

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
    
    def verify_output_block(self, children: List[Any]) -> Dict[str, Any]:
        """Create VerificationOutputNode and optional timeseries config from settings."""
        settings = children[0] if children else {}

        # Extract timeseries_plot_config if present (it's a separate key)
        timeseries_config = settings.pop("timeseries_plot_config", None)

        output_node = VerificationOutputNode(
            format=settings.get("format", "json"),
            file_path=settings.get("file_path", "output/verification_results.json"),
            include_counterexample=settings.get("include_counterexample", True),
            generate_plots=settings.get("generate_plots", False),
        )

        # Return both output node and timeseries config
        return {"output": output_node, "timeseries_plot_config": timeseries_config}
    
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
            "timeseries_observables": [],
            "check": VerificationCheckNode(),
            "output": VerificationOutputNode(),
            "timeseries_plot_config": None,
        }

        for child in children:
            if isinstance(child, list):
                if child and isinstance(child[0], ModelImportNode):
                    result["models"] = child
                elif child and isinstance(child[0], LabelNode):
                    result["labels"] = child
                elif child and isinstance(child[0], ObservableNode):
                    result["observables"] = child
                elif child and isinstance(child[0], TimeseriesObservableNode):
                    result["timeseries_observables"] = child
                elif child and isinstance(child[0], int):
                    # List of seeds from single_seed, multi_seed, or seed_range
                    result["seeds"] = child
            elif isinstance(child, VerificationCheckNode):
                result["check"] = child
            elif isinstance(child, VerificationOutputNode):
                result["output"] = child
            elif isinstance(child, dict):
                # Output block now returns dict with output and timeseries_plot_config
                if "output" in child:
                    result["output"] = child["output"]
                if "timeseries_plot_config" in child and child["timeseries_plot_config"] is not None:
                    result["timeseries_plot_config"] = child["timeseries_plot_config"]

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
            timeseries_observables=body["timeseries_observables"],
            check=body["check"],
            output=body["output"],
            timeseries_plot_config=body["timeseries_plot_config"],
        )
    
    def verification_file(self, children: List[Any]) -> VerificationNode:
        """Return the verification node."""
        return children[0]

    # =========================================================================
    # Analysis: Models Block
    # =========================================================================

    def analysis_model_import(self, children: List[Any]) -> AnalysisModelNode:
        """Handle import Name from "path" """
        return AnalysisModelNode(name=children[0], path=children[1])

    def analysis_models_block(self, children: List[Any]) -> List[AnalysisModelNode]:
        """Collect all analysis model imports."""
        return [c for c in children if isinstance(c, AnalysisModelNode)]

    # =========================================================================
    # Analysis: Metrics Block
    # =========================================================================

    def analysis_metric_type(self, children: List[Any]) -> Dict[str, str]:
        """Handle type: het"""
        return {"metric_type": children[0]}

    def analysis_feature_list(self, children: List[Any]) -> List[str]:
        """Handle [feat1, feat2, ...]"""
        return [str(c) for c in children]

    def analysis_metric_features(self, children: List[Any]) -> Dict[str, List[str]]:
        """Handle features: [list]"""
        return {"features": children[0]}

    def analysis_metric_setting(self, children: List[Any]) -> Dict[str, Any]:
        """Single analysis metric setting."""
        return children[0]

    def analysis_metrics_block(self, children: List[Any]) -> AnalysisMetricsNode:
        """Create AnalysisMetricsNode from settings."""
        settings = {}
        for child in children:
            if isinstance(child, dict):
                settings.update(child)
        return AnalysisMetricsNode(
            metric_type=settings.get("metric_type", "het"),
            features=settings.get("features", AnalysisMetricsNode().features),
        )

    # =========================================================================
    # Analysis: Runtime Block
    # =========================================================================

    def analysis_rt_end_time(self, children: List[Any]) -> Dict[str, float]:
        """Handle end_time: N"""
        return {"end_time": float(children[0])}

    def analysis_rt_seeds(self, children: List[Any]) -> Dict[str, List[int]]:
        """Handle seeds: [list]"""
        return {"seeds": children[0]}

    def analysis_rt_single_seed(self, children: List[Any]) -> Dict[str, List[int]]:
        """Handle seed: N"""
        return {"seeds": [int(children[0])]}

    def analysis_rt_seed_range(self, children: List[Any]) -> Dict[str, List[int]]:
        """Handle seed_range: N to M"""
        start = int(children[0])
        end = int(children[1])
        return {"seeds": list(range(start, end + 1))}

    def analysis_rt_time_var(self, children: List[Any]) -> Dict[str, str]:
        """Handle time_var: "var_name" """
        return {"time_var": children[0]}

    def analysis_runtime_setting(self, children: List[Any]) -> Dict[str, Any]:
        """Single analysis runtime setting."""
        return children[0]

    def analysis_runtime_block(self, children: List[Any]) -> AnalysisRuntimeNode:
        """Create AnalysisRuntimeNode from settings."""
        settings = {}
        for child in children:
            if isinstance(child, dict):
                settings.update(child)
        return AnalysisRuntimeNode(
            end_time=settings.get("end_time", 1000.0),
            seeds=settings.get("seeds", [42, 123, 456]),
            time_var=settings.get("time_var", "sim_clocktime"),
        )

    # =========================================================================
    # Analysis: Regression Block
    # =========================================================================

    def analysis_reg_target(self, children: List[Any]) -> Dict[str, str]:
        """Handle target: exec_time_sec_mean"""
        return {"target": children[0]}

    def analysis_reg_predictors(self, children: List[Any]) -> Dict[str, List[str]]:
        """Handle predictors: [list]"""
        return {"predictors": children[0]}

    def analysis_reg_method(self, children: List[Any]) -> Dict[str, str]:
        """Handle method: ols"""
        return {"method": children[0]}

    def analysis_regression_setting(self, children: List[Any]) -> Dict[str, Any]:
        """Single analysis regression setting."""
        return children[0]

    def analysis_regression_block(self, children: List[Any]) -> AnalysisRegressionNode:
        """Create AnalysisRegressionNode from settings."""
        settings = {}
        for child in children:
            if isinstance(child, dict):
                settings.update(child)
        return AnalysisRegressionNode(
            target=settings.get("target", "exec_time_sec_mean"),
            predictors=settings.get("predictors", ["total_het", "total_updates"]),
            method=settings.get("method", "ols"),
        )

    # =========================================================================
    # Analysis: Output Block
    # =========================================================================

    def analysis_out_format(self, children: List[Any]) -> Dict[str, str]:
        """Handle format: "json" """
        return {"format": children[0]}

    def analysis_out_path(self, children: List[Any]) -> Dict[str, str]:
        """Handle file_path: "path" """
        return {"file_path": children[0]}

    def analysis_out_generate_plots(self, children: List[Any]) -> Dict[str, bool]:
        """Handle generate_plots: true/false"""
        return {"generate_plots": children[0]}

    def analysis_output_setting(self, children: List[Any]) -> Dict[str, Any]:
        """Single analysis output setting."""
        return children[0]

    def analysis_output_block(self, children: List[Any]) -> AnalysisOutputNode:
        """Create AnalysisOutputNode from settings."""
        settings = {}
        for child in children:
            if isinstance(child, dict):
                settings.update(child)
        return AnalysisOutputNode(
            format=settings.get("format", "json"),
            file_path=settings.get("file_path", "output/complexity_analysis/"),
            generate_plots=settings.get("generate_plots", True),
        )

    # =========================================================================
    # Analysis: Main Structure
    # =========================================================================

    def analysis_body(self, children: List[Any]) -> Dict[str, Any]:
        """Collect analysis body components."""
        result = {
            "models": [],
            "metrics": AnalysisMetricsNode(),
            "runtime": AnalysisRuntimeNode(),
            "regression": None,  # None means skip regression
            "output": AnalysisOutputNode(),
        }

        for child in children:
            if isinstance(child, list) and child and isinstance(child[0], AnalysisModelNode):
                result["models"] = child
            elif isinstance(child, AnalysisMetricsNode):
                result["metrics"] = child
            elif isinstance(child, AnalysisRuntimeNode):
                result["runtime"] = child
            elif isinstance(child, AnalysisRegressionNode):
                result["regression"] = child
            elif isinstance(child, AnalysisOutputNode):
                result["output"] = child

        return result

    def analysis_decl(self, children: List[Any]) -> AnalysisNode:
        """Create AnalysisNode from declaration."""
        name = children[0]
        body = children[1]

        return AnalysisNode(
            name=name,
            models=body["models"],
            metrics=body["metrics"],
            runtime=body["runtime"],
            regression=body["regression"],
            output=body["output"],
        )

    def analysis_file(self, children: List[Any]) -> AnalysisNode:
        """Return the analysis node."""
        return children[0]

    # =========================================================================
    # Complexity Analysis: Models Block
    # =========================================================================

    def complexity_simasm_path(self, children: List[Any]) -> Dict[str, str]:
        """Handle simasm: "path" """
        return {"simasm_path": children[0]}

    def complexity_event_graph_path(self, children: List[Any]) -> Dict[str, str]:
        """Handle event_graph: "path" """
        return {"event_graph_path": children[0]}

    def complexity_json_spec_path(self, children: List[Any]) -> Dict[str, str]:
        """Handle json_spec: "path" (alias for event_graph)"""
        return {"event_graph_path": children[0]}

    def complexity_model_path(self, children: List[Any]) -> Dict[str, str]:
        """Single complexity model path setting."""
        return children[0]

    def complexity_model_paths(self, children: List[Any]) -> Dict[str, str]:
        """Merge all complexity model path settings."""
        result = {}
        for setting in children:
            if isinstance(setting, dict):
                result.update(setting)
        return result

    def complexity_model_decl(self, children: List[Any]) -> ComplexityModelNode:
        """Create ComplexityModelNode from declaration."""
        name = children[0]
        paths = children[1] if len(children) > 1 else {}
        return ComplexityModelNode(
            name=name,
            simasm_path=paths.get("simasm_path", ""),
            event_graph_path=paths.get("event_graph_path", ""),
        )

    def complexity_simasm_dir(self, children: List[Any]) -> Dict[str, str]:
        """Handle simasm_dir: "path" """
        return {"simasm_dir": children[0]}

    def complexity_json_dir(self, children: List[Any]) -> Dict[str, str]:
        """Handle json_dir: "path" """
        return {"json_dir": children[0]}

    def complexity_model_dir(self, children: List[Any]) -> Dict[str, str]:
        """Single complexity model directory setting."""
        return children[0]

    def complexity_models_block(self, children: List[Any]) -> Dict[str, Any]:
        """Collect model declarations and directory settings."""
        models = [c for c in children if isinstance(c, ComplexityModelNode)]
        dirs = {}
        for c in children:
            if isinstance(c, dict):
                dirs.update(c)
        return {"models": models, **dirs}

    # =========================================================================
    # Complexity Analysis: Metrics Block
    # =========================================================================

    def complexity_het_static(self, children: List[Any]) -> Dict[str, bool]:
        """Handle het_static: true/false"""
        return {"het_static": children[0]}

    def complexity_het_path_based(self, children: List[Any]) -> Dict[str, bool]:
        """Handle het_path_based: true/false"""
        return {"het_path_based": children[0]}

    def complexity_max_cycles(self, children: List[Any]) -> Dict[str, int]:
        """Handle max_cycle_traversals: N"""
        return {"max_cycle_traversals": int(children[0])}

    def complexity_structural(self, children: List[Any]) -> Dict[str, bool]:
        """Handle structural: true/false"""
        return {"structural": children[0]}

    def complexity_component_breakdown(self, children: List[Any]) -> Dict[str, bool]:
        """Handle component_breakdown: true/false"""
        return {"component_breakdown": children[0]}

    def complexity_smc(self, children: List[Any]) -> Dict[str, bool]:
        """Handle smc: true/false"""
        return {"smc": children[0]}

    def complexity_cc(self, children: List[Any]) -> Dict[str, bool]:
        """Handle cc: true/false"""
        return {"cc": children[0]}

    def complexity_loc(self, children: List[Any]) -> Dict[str, bool]:
        """Handle loc: true/false"""
        return {"loc": children[0]}

    def complexity_kc(self, children: List[Any]) -> Dict[str, bool]:
        """Handle kc: true/false"""
        return {"kc": children[0]}

    def complexity_metric_setting(self, children: List[Any]) -> Dict[str, Any]:
        """Single complexity metric setting."""
        return children[0]

    def complexity_metrics_block(self, children: List[Any]) -> ComplexityMetricsNode:
        """Create ComplexityMetricsNode from settings."""
        settings = {}
        for child in children:
            if isinstance(child, dict):
                settings.update(child)
        return ComplexityMetricsNode(
            het_static=settings.get("het_static", True),
            het_path_based=settings.get("het_path_based", True),
            max_cycle_traversals=settings.get("max_cycle_traversals", 1),
            structural=settings.get("structural", True),
            component_breakdown=settings.get("component_breakdown", True),
            smc=settings.get("smc", True),
            cc=settings.get("cc", True),
            loc=settings.get("loc", True),
            kc=settings.get("kc", True),
        )

    # =========================================================================
    # Complexity Analysis: Output Block
    # =========================================================================

    def complexity_out_format(self, children: List[Any]) -> Dict[str, str]:
        """Handle format: "json" """
        return {"format": children[0]}

    def complexity_out_path(self, children: List[Any]) -> Dict[str, str]:
        """Handle file_path: "path" """
        return {"file_path": children[0]}

    def complexity_out_summary(self, children: List[Any]) -> Dict[str, bool]:
        """Handle generate_summary: true/false"""
        return {"generate_summary": children[0]}

    def complexity_out_include_paths(self, children: List[Any]) -> Dict[str, bool]:
        """Handle include_paths: true/false"""
        return {"include_paths": children[0]}

    def complexity_output_setting(self, children: List[Any]) -> Dict[str, Any]:
        """Single complexity output setting."""
        return children[0]

    def complexity_output_block(self, children: List[Any]) -> ComplexityOutputNode:
        """Create ComplexityOutputNode from settings."""
        settings = {}
        for child in children:
            if isinstance(child, dict):
                settings.update(child)
        return ComplexityOutputNode(
            format=settings.get("format", "json"),
            file_path=settings.get("file_path", "output/complexity_results.json"),
            generate_summary=settings.get("generate_summary", True),
            include_paths=settings.get("include_paths", False),
        )

    # =========================================================================
    # Complexity Analysis: Main Structure
    # =========================================================================

    def complexity_body(self, children: List[Any]) -> Dict[str, Any]:
        """Collect complexity body components."""
        result = {
            "models": [],
            "metrics": ComplexityMetricsNode(),
            "output": ComplexityOutputNode(),
            "simasm_dir": "",
            "json_dir": "",
        }

        for child in children:
            if isinstance(child, dict) and "models" in child:
                # From complexity_models_block — contains models list + optional dir paths
                result["models"] = child["models"]
                if "simasm_dir" in child:
                    result["simasm_dir"] = child["simasm_dir"]
                if "json_dir" in child:
                    result["json_dir"] = child["json_dir"]
            elif isinstance(child, list) and child and isinstance(child[0], ComplexityModelNode):
                result["models"] = child
            elif isinstance(child, ComplexityMetricsNode):
                result["metrics"] = child
            elif isinstance(child, ComplexityOutputNode):
                result["output"] = child

        return result

    def complexity_decl(self, children: List[Any]) -> ComplexityNode:
        """Create ComplexityNode from declaration."""
        name = children[0]
        body = children[1]

        return ComplexityNode(
            name=name,
            models=body["models"],
            metrics=body["metrics"],
            output=body["output"],
            simasm_dir=body.get("simasm_dir", ""),
            json_dir=body.get("json_dir", ""),
        )

    def complexity_file(self, children: List[Any]) -> ComplexityNode:
        """Return the complexity node."""
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


class AnalysisParser:
    """
    Parser for analysis specification files.

    Usage:
        parser = AnalysisParser()
        analysis = parser.parse(code)
        # or
        analysis = parser.parse_file("complexity.simasm")
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
            start="analysis_file",
        )

    def parse(self, code: str) -> AnalysisNode:
        """
        Parse analysis specification code.

        Args:
            code: Analysis specification source code

        Returns:
            AnalysisNode AST
        """
        return self._parser.parse(code)

    def parse_file(self, path: str) -> AnalysisNode:
        """
        Parse analysis specification from file.

        Args:
            path: Path to .simasm analysis file

        Returns:
            AnalysisNode AST
        """
        with open(path, encoding="utf-8") as f:
            code = f.read()
        return self.parse(code)


class ComplexityParser:
    """
    Parser for complexity analysis specification files.

    Usage:
        parser = ComplexityParser()
        complexity = parser.parse(code)
        # or
        complexity = parser.parse_file("complexity.simasm")
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
            start="complexity_file",
        )

    def parse(self, code: str) -> ComplexityNode:
        """
        Parse complexity specification code.

        Args:
            code: Complexity specification source code

        Returns:
            ComplexityNode AST
        """
        return self._parser.parse(code)

    def parse_file(self, path: str) -> ComplexityNode:
        """
        Parse complexity specification from file.

        Args:
            path: Path to .simasm complexity file

        Returns:
            ComplexityNode AST
        """
        with open(path, encoding="utf-8") as f:
            code = f.read()
        return self.parse(code)


class SpecificationParser:
    """
    Universal parser that auto-detects experiment, verification, analysis, or complexity specs.

    Usage:
        parser = SpecificationParser()
        spec = parser.parse(code)  # Returns ExperimentNode, VerificationNode, AnalysisNode, or ComplexityNode
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

    def parse(self, code: str) -> Union[ExperimentNode, VerificationNode, AnalysisNode, ComplexityNode]:
        """
        Parse specification code, auto-detecting type.

        Args:
            code: Specification source code

        Returns:
            ExperimentNode, VerificationNode, AnalysisNode, or ComplexityNode AST
        """
        return self._parser.parse(code)

    def parse_file(self, path: str) -> Union[ExperimentNode, VerificationNode, AnalysisNode, ComplexityNode]:
        """
        Parse specification from file, auto-detecting type.

        Args:
            path: Path to .simasm specification file

        Returns:
            ExperimentNode, VerificationNode, AnalysisNode, or ComplexityNode AST
        """
        with open(path, encoding="utf-8") as f:
            code = f.read()
        return self.parse(code)