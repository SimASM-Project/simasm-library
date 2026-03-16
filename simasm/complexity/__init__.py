"""
SimASM Complexity Analysis Module.

Provides HET (Hierarchical Execution Time) complexity metrics based on
Nowack (2000) "Complexity Theory via Abstract State Machines".

This module implements:
- Static HET: Sum of rule complexities
- Path-Based HET: Average complexity over entity traversal paths
- Structural metrics: Yucesan & Schruben (1998) Event Graph metrics

Main Entry Points:
    analyze_complexity: Complete complexity analysis
    compute_het_static: Static HET only
    compute_het_path_based: Path-Based HET
    get_structural_metrics: Event Graph structural metrics
    get_all_metrics: All metrics as flat dict

Example:
    from simasm.complexity import analyze_complexity

    result = analyze_complexity("model.simasm", json_spec_path="model.json")
    print(f"Static HET: {result.het_static}")
    print(f"Path-Based HET: {result.het_path_avg}")
"""

from .simasm_het_analyzer import (
    HETCalculator,
    HETResult,
    RuleAnalysis,
    ProgramAnalysis,
    ComplexityResult,
    analyze_simasm,
    print_analysis,
    analysis_to_dict,
)

from .api import (
    analyze_complexity,
    compute_het_static,
    compute_het_path_based,
    get_structural_metrics,
    get_all_metrics,
)

from .event_graph_parser import (
    EventGraph,
    Vertex,
    Edge,
    parse_event_graph,
    parse_event_graph_from_dict,
)

from .path_enumerator import (
    enumerate_paths,
    calculate_path_het,
    calculate_path_based_het,
    get_path_statistics,
)

__all__ = [
    # Main analysis functions (API)
    'analyze_complexity',
    'compute_het_static',
    'compute_het_path_based',
    'get_structural_metrics',
    'get_all_metrics',

    # Core classes
    'HETCalculator',
    'HETResult',
    'RuleAnalysis',
    'ProgramAnalysis',
    'ComplexityResult',

    # Event Graph parsing
    'EventGraph',
    'Vertex',
    'Edge',
    'parse_event_graph',
    'parse_event_graph_from_dict',

    # Path enumeration
    'enumerate_paths',
    'calculate_path_het',
    'calculate_path_based_het',
    'get_path_statistics',

    # Legacy functions
    'analyze_simasm',
    'print_analysis',
    'analysis_to_dict',
]
