"""
SimASM experimenter module.

Provides experiment, verification, analysis, and complexity specification parsing and execution.

Parsing API:
- ExperimentParser: Parse experiment specifications
- VerificationParser: Parse verification specifications
- AnalysisParser: Parse complexity analysis specifications (with runtime/regression)
- ComplexityParser: Parse complexity metric specifications (metrics only)
- SpecificationParser: Auto-detect and parse any type
- AST nodes: ExperimentNode, VerificationNode, AnalysisNode, ComplexityNode, etc.

Experiment Execution API:
- ExperimenterEngine: Execute experiment specifications
- SimASMModel: Adapter for SimASM models
- run_experiment: Convenience function

Verification Execution API:
- VerificationEngine: Execute verification specifications
- run_verification: Convenience function

Analysis Execution API:
- AnalysisEngine: Execute complexity analysis specifications (with runtime/regression)
- run_analysis: Convenience function

Complexity Execution API:
- ComplexityEngine: Execute complexity metric specifications
- run_complexity: Convenience function

Usage:
    # Run experiment from file
    from simasm.experimenter import run_experiment
    result = run_experiment("experiments/mmn.simasm")

    # Run verification from file
    from simasm.experimenter import run_verification
    result = run_verification("verify/eg_vs_acd.simasm")
    if result.is_equivalent:
        print("Models are stutter equivalent!")

    # Run complexity analysis from file
    from simasm.experimenter import run_analysis
    result = run_analysis("analysis/tandem_complexity.simasm")
    print(f"R² = {result.r_squared:.3f}")

    # Run complexity metrics from file
    from simasm.experimenter import run_complexity
    result = run_complexity("specs/benchmark_complexity.simasm")
    for model in result.models:
        print(f"{model['name']}: HET={model['het_static']}")
"""

from simasm.experimenter.ast import (
    # Experiment AST
    ExperimentNode,
    ReplicationNode,
    StatisticNode,
    ExperimentOutputNode,
    # Verification AST
    ModelImportNode,
    LabelNode,
    ObservableNode,
    VerificationCheckNode,
    VerificationOutputNode,
    VerificationNode,
    # Analysis AST
    AnalysisModelNode,
    AnalysisMetricsNode,
    AnalysisRuntimeNode,
    AnalysisRegressionNode,
    AnalysisOutputNode,
    AnalysisNode,
    # Complexity AST
    ComplexityModelNode,
    ComplexityMetricsNode,
    ComplexityOutputNode,
    ComplexityNode,
)
from simasm.experimenter.transformer import (
    ExperimentParser,
    VerificationParser,
    AnalysisParser,
    ComplexityParser,
    SpecificationParser,
    ExperimentTransformer,
)
from simasm.experimenter.engine import (
    # Experiment
    ExperimenterEngine,
    SimASMModel,
    run_experiment,
    run_experiment_from_node,
    # Verification
    VerificationEngine,
    run_verification,
    run_verification_from_node,
    # Analysis
    AnalysisEngine,
    AnalysisResult,
    run_analysis,
    run_analysis_from_node,
    # Complexity
    ComplexityEngine,
    ComplexityResult,
    run_complexity,
    run_complexity_from_node,
)

__all__ = [
    # Experiment AST nodes
    'ExperimentNode',
    'ReplicationNode',
    'StatisticNode',
    'ExperimentOutputNode',
    # Verification AST nodes
    'ModelImportNode',
    'LabelNode',
    'ObservableNode',
    'VerificationCheckNode',
    'VerificationOutputNode',
    'VerificationNode',
    # Analysis AST nodes
    'AnalysisModelNode',
    'AnalysisMetricsNode',
    'AnalysisRuntimeNode',
    'AnalysisRegressionNode',
    'AnalysisOutputNode',
    'AnalysisNode',
    # Complexity AST nodes
    'ComplexityModelNode',
    'ComplexityMetricsNode',
    'ComplexityOutputNode',
    'ComplexityNode',
    # Parsers
    'ExperimentParser',
    'VerificationParser',
    'AnalysisParser',
    'ComplexityParser',
    'SpecificationParser',
    'ExperimentTransformer',
    # Experiment Engine
    'ExperimenterEngine',
    'SimASMModel',
    'run_experiment',
    'run_experiment_from_node',
    # Verification Engine
    'VerificationEngine',
    'run_verification',
    'run_verification_from_node',
    # Analysis Engine
    'AnalysisEngine',
    'AnalysisResult',
    'run_analysis',
    'run_analysis_from_node',
    # Complexity Engine
    'ComplexityEngine',
    'ComplexityResult',
    'run_complexity',
    'run_complexity_from_node',
]
