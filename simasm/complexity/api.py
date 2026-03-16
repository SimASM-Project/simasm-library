"""
Public API for SimASM complexity analysis.

This module provides the main entry points for complexity analysis:
- analyze_complexity: Complete analysis with all metrics
- compute_het_static: Static HET only
- compute_het_path_based: Path-Based HET
- get_structural_metrics: Event Graph structural metrics
- get_all_metrics: All metrics as flat dict (for DataFrames)

Usage:
    from simasm.complexity import analyze_complexity, get_all_metrics

    result = analyze_complexity("model.simasm", json_path="model.json")
    print(f"Static HET: {result.het_static}")
    print(f"Path-Based HET: {result.het_path_avg}")

    # For DataFrame construction
    metrics = get_all_metrics("model.simasm", "model.json")
    df = pd.DataFrame([metrics])
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, Union, List, Tuple

from .simasm_het_analyzer import (
    Lexer,
    Parser,
    HETCalculator,
    RuleAnalysis,
    ComplexityResult,
    analyze_simasm,
)
from .event_graph_parser import parse_event_graph, EventGraph
from .path_enumerator import calculate_path_based_het, enumerate_paths
from .acd_path_enumerator import parse_acd_graph, compute_acd_smc, enumerate_acd_paths
from .devs_path_enumerator import parse_devs_graph, compute_devs_smc, enumerate_devs_paths, build_component_het


def _detect_formalism(json_path: str) -> str:
    """Detect formalism: 'eg', 'acd', or 'devs'."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            spec = json.load(f)
        if 'atomic_models' in spec:
            return 'devs'
        elif 'activities' in spec and 'vertices' not in spec:
            return 'acd'
        else:
            return 'eg'
    except Exception:
        return 'eg'


def _is_acd_spec(json_path: str) -> bool:
    """Detect whether a JSON spec is an ACD model (has 'activities') vs EG (has 'vertices')."""
    return _detect_formalism(json_path) == 'acd'


def _build_activity_het(event_het: Dict[str, int]) -> Dict[str, int]:
    """Build activity-level HET from per-rule HET.

    ACD rules are named at_begin_action_{name} and at_end_action_{name}.
    Combines both into a single activity HET entry.
    """
    activity_het = {}
    # Group rules by activity name
    for rule_name, het in event_het.items():
        name_lower = rule_name.lower()
        # Extract activity name from at_begin_action_X or at_end_action_X
        for prefix in ('at_begin_action_', 'at_end_action_'):
            if name_lower.startswith(prefix):
                act_name = name_lower[len(prefix):]
                if act_name not in activity_het:
                    activity_het[act_name] = 0
                activity_het[act_name] += het
                break
    return activity_het


def _normalize_name(name):
    """Normalize event name: lowercase, collapse multiple underscores."""
    return name.lower().replace('__', '_')


def _lookup_het(v, event_het):
    """Look up event HET by name, trying multiple formats."""
    # Direct lookups
    for key in [v, v.lower(), f"event_{v.lower()}", v.capitalize()]:
        if key in event_het:
            return event_het[key]

    # Normalized lookup (handles double underscores in SimASM rule names)
    norm_v = _normalize_name(v)
    for key in event_het:
        if _normalize_name(key) == norm_v or _normalize_name(key) == f"event_{norm_v}":
            return event_het[key]

    return 0


def compute_smc(eg, event_het, het_control):
    """Compute path-based SMC: deduplicated event costs + control overhead.

    Algorithm:
      1. Enumerate all source-to-sink paths on acyclic subgraph (back-edges removed)
      2. Remove duplicate paths
      3. Collect unique events across all paths
      4. Sum their costs
      5. Add control overhead
    """
    paths = enumerate_paths(eg, max_cycle_traversals=0)
    if not paths:
        return het_control  # Only control cost if no paths

    # Remove duplicate paths
    unique_paths = list({tuple(p) for p in paths})

    # Collect unique events across all paths
    unique_events = set()
    for p in unique_paths:
        unique_events.update(p)

    # Sum deduplicated event costs
    c_entity = sum(_lookup_het(v, event_het) for v in unique_events)

    # SMC = entity costs + control overhead
    smc = c_entity + het_control
    return smc


def analyze_complexity(
    source_or_path: Union[str, Path],
    json_spec_path: Optional[Union[str, Path]] = None,
    model_name: Optional[str] = None
) -> ComplexityResult:
    """
    Perform complete complexity analysis on a SimASM model.

    This is the main entry point that computes all complexity metrics:
    - Static HET (sum of all rule complexities)
    - Path-Based HET (average over enumerated paths)
    - Structural metrics (|V|, |E|, density, cyclomatic number)
    - Component breakdown (updates, conditionals, etc.)

    Args:
        source_or_path: SimASM source code string or path to .simasm file
        json_spec_path: Path to Event Graph JSON specification (required for path-based HET)
        model_name: Optional model identifier (defaults to filename or "model")

    Returns:
        ComplexityResult with all computed metrics

    Example:
        result = analyze_complexity(
            "path/to/model.simasm",
            json_spec_path="path/to/model.json"
        )
        print(f"Static HET: {result.het_static}")
        print(f"Path-Based HET: {result.het_path_avg}")
        print(f"|V|={result.vertex_count}, |E|={result.edge_count}")
    """
    # Determine if input is path or source
    path = Path(source_or_path) if not isinstance(source_or_path, Path) else source_or_path

    if path.exists() and path.suffix == '.simasm':
        source = path.read_text(encoding='utf-8')
        source_file = str(path)
        if model_name is None:
            model_name = path.stem
    else:
        source = str(source_or_path)
        source_file = ""
        if model_name is None:
            model_name = "model"

    # Parse SimASM and calculate static HET
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    program_ast = parser.parse()

    calculator = HETCalculator()

    # Calculate per-rule HET
    rule_analyses: List[RuleAnalysis] = []
    event_het: Dict[str, int] = {}  # Map event name to HET
    het_event_total = 0
    het_control_total = 0

    for rule_node in parser.rules:
        result = calculator.calculate(rule_node)
        rule_name = rule_node.value

        analysis = RuleAnalysis(
            name=rule_name,
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

        # Classify as event or control rule
        if calculator.is_control_rule(rule_name):
            het_control_total += result.het
        else:
            het_event_total += result.het
            # Store event HET with various name formats for matching
            event_het[rule_name] = result.het
            event_het[rule_name.lower()] = result.het
            # Extract event name (remove "event_" prefix if present)
            if rule_name.lower().startswith('event_'):
                event_name = rule_name[6:]
                event_het[event_name] = result.het
                event_het[event_name.lower()] = result.het
                event_het[event_name.capitalize()] = result.het

    het_static = het_event_total + het_control_total

    # Aggregate metrics
    total_updates = sum(r.updates for r in rule_analyses)
    total_conditionals = sum(r.conditionals for r in rule_analyses)
    total_let_bindings = sum(r.let_bindings for r in rule_analyses)
    total_function_calls = sum(r.function_calls for r in rule_analyses)
    total_new_entities = sum(r.new_entities for r in rule_analyses)
    total_list_operations = sum(r.list_operations for r in rule_analyses)

    # Initialize structural metrics and path-based HET
    vertex_count = 0
    edge_count = 0
    edge_density = 0.0
    cyclomatic_number = 0
    has_cycles = False
    het_path_avg = 0.0
    num_paths = 0
    path_breakdown: List[Tuple[List[str], int]] = []
    smc_value = 0.0

    # Parse JSON spec for structural metrics and path-based SMC
    if json_spec_path:
        json_path_str = str(json_spec_path)
        if os.path.exists(json_path_str):
            formalism = _detect_formalism(json_path_str)

            if formalism == 'devs':
                # DEVS model: use DEVS path enumerator
                devs_graph = parse_devs_graph(json_path_str)

                # DEVS structural metrics (component/coupling counts)
                vertex_count = devs_graph.V
                edge_count = devs_graph.E
                edge_density = devs_graph.edge_density
                cyclomatic_number = devs_graph.cyclomatic_number
                has_cycles = devs_graph.has_cycle()

                # Build component-level HET from per-rule HET
                component_het = build_component_het(event_het)

                # Path-Based HET for DEVS
                devs_paths = enumerate_devs_paths(devs_graph, max_cycle_traversals=1)
                if devs_paths:
                    path_hets = []
                    for p in devs_paths:
                        p_het = sum(component_het.get(c.lower(), 0) for c in p)
                        path_hets.append((p, p_het))
                    het_path_avg = sum(h for _, h in path_hets) / len(path_hets)
                    path_breakdown = path_hets
                    num_paths = len(path_hets)

                # Path-based SMC for DEVS
                smc_value = compute_devs_smc(devs_graph, component_het, het_control_total)

            elif formalism == 'acd':
                # ACD model: use ACD path enumerator
                acd = parse_acd_graph(json_path_str)

                # ACD structural metrics (activity/queue counts)
                vertex_count = len(acd.activities)
                edge_count = sum(len(succs) for succs in acd.adjacency.values())
                edge_density = edge_count / (vertex_count ** 2) if vertex_count > 0 else 0.0
                cyclomatic_number = edge_count - vertex_count + 2
                has_cycles = acd.has_cycle()

                # Build activity-level HET from per-rule HET
                activity_het = _build_activity_het(event_het)

                # Path-Based HET for ACD
                acd_paths = enumerate_acd_paths(acd, max_cycle_traversals=1)
                if acd_paths:
                    path_hets = []
                    for p in acd_paths:
                        p_het = sum(activity_het.get(a.lower(), 0) for a in p)
                        path_hets.append((p, p_het))
                    het_path_avg = sum(h for _, h in path_hets) / len(path_hets)
                    path_breakdown = path_hets
                    num_paths = len(path_hets)

                # Path-based SMC for ACD
                smc_value = compute_acd_smc(acd, activity_het, het_control_total)

            else:
                # EG model: use EG path enumerator
                eg = parse_event_graph(json_path_str)

                # Structural metrics
                vertex_count = eg.V
                edge_count = eg.E
                edge_density = eg.edge_density
                cyclomatic_number = eg.cyclomatic_number
                has_cycles = eg.has_cycle()

                # Path-Based HET
                het_path_avg, path_breakdown = calculate_path_based_het(
                    eg=eg,
                    event_het=event_het,
                    control_step_cost=calculator.COST_CONTROL_STEP,
                    max_cycle_traversals=1
                )
                num_paths = len(path_breakdown)

                # Path-based SMC
                smc_value = compute_smc(eg, event_het, het_control_total)

    return ComplexityResult(
        model_name=model_name,
        source_file=source_file,
        het_static=het_static,
        het_event=het_event_total,
        het_control=het_control_total,
        smc=smc_value,
        het_path_avg=het_path_avg,
        num_paths=num_paths,
        path_breakdown=path_breakdown,
        total_rules=len(rule_analyses),
        total_updates=total_updates,
        total_conditionals=total_conditionals,
        total_let_bindings=total_let_bindings,
        total_function_calls=total_function_calls,
        total_new_entities=total_new_entities,
        total_list_operations=total_list_operations,
        vertex_count=vertex_count,
        edge_count=edge_count,
        edge_density=edge_density,
        cyclomatic_number=cyclomatic_number,
        has_cycles=has_cycles,
        rules=rule_analyses
    )


def compute_het_static(source_or_path: Union[str, Path]) -> int:
    """
    Compute Static HET only (sum of all rule complexities).

    This is a convenience function when you only need static HET
    without path-based analysis.

    Args:
        source_or_path: SimASM source code or path to .simasm file

    Returns:
        Static HET value
    """
    result = analyze_complexity(source_or_path)
    return result.het_static


def compute_het_path_based(
    source_or_path: Union[str, Path],
    json_spec_path: Union[str, Path],
    max_cycle_traversals: int = 1
) -> float:
    """
    Compute Path-Based HET (average over enumerated paths).

    Args:
        source_or_path: SimASM source code or path to .simasm file
        json_spec_path: Path to Event Graph JSON specification
        max_cycle_traversals: Maximum cycle traversals in path enumeration

    Returns:
        Path-Based HET (average)
    """
    result = analyze_complexity(source_or_path, json_spec_path)
    return result.het_path_avg


def get_structural_metrics(json_spec_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Extract structural metrics from Event Graph JSON.

    These are the Yucesan & Schruben (1998) graph-theoretic metrics.

    Args:
        json_spec_path: Path to Event Graph JSON specification

    Returns:
        Dict with keys:
        - vertex_count: |V|
        - edge_count: |E|
        - edge_density: |E| / |V|^2
        - cyclomatic_number: |E| - |V| + 2
        - has_cycles: Whether graph contains cycles
    """
    eg = parse_event_graph(str(json_spec_path))
    return {
        'vertex_count': eg.V,
        'edge_count': eg.E,
        'edge_density': eg.edge_density,
        'cyclomatic_number': eg.cyclomatic_number,
        'has_cycles': eg.has_cycle()
    }


def get_all_metrics(
    simasm_path: Union[str, Path],
    json_spec_path: Union[str, Path]
) -> Dict[str, Any]:
    """
    Get all complexity metrics as a flat dictionary.

    This is suitable for constructing pandas DataFrames for analysis.

    Args:
        simasm_path: Path to SimASM file
        json_spec_path: Path to Event Graph JSON specification

    Returns:
        Flat dict with all metrics (no nested structures)
    """
    result = analyze_complexity(simasm_path, json_spec_path)

    return {
        'model_name': result.model_name,
        'het_static': result.het_static,
        'het_event': result.het_event,
        'het_control': result.het_control,
        'smc': result.smc,
        'het_path_avg': result.het_path_avg,
        'num_paths': result.num_paths,
        'total_rules': result.total_rules,
        'total_updates': result.total_updates,
        'total_conditionals': result.total_conditionals,
        'total_let_bindings': result.total_let_bindings,
        'total_function_calls': result.total_function_calls,
        'total_new_entities': result.total_new_entities,
        'total_list_operations': result.total_list_operations,
        'vertex_count': result.vertex_count,
        'edge_count': result.edge_count,
        'edge_density': result.edge_density,
        'cyclomatic_number': result.cyclomatic_number,
        'has_cycles': result.has_cycles
    }
