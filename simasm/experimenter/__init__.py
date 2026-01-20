"""
SimASM experimenter module.

Provides experiment and verification specification parsing and execution.

Parsing API:
- ExperimentParser: Parse experiment specifications
- VerificationParser: Parse verification specifications
- SpecificationParser: Auto-detect and parse either type
- AST nodes: ExperimentNode, VerificationNode, etc.

Experiment Execution API:
- ExperimenterEngine: Execute experiment specifications
- SimASMModel: Adapter for SimASM models
- run_experiment: Convenience function

Verification Execution API:
- VerificationEngine: Execute verification specifications
- run_verification: Convenience function

Usage:
    # Run experiment from file
    from simasm.experimenter import run_experiment
    result = run_experiment("experiments/mmn.simasm")
    
    # Run verification from file
    from simasm.experimenter import run_verification
    result = run_verification("verify/eg_vs_acd.simasm")
    if result.is_equivalent:
        print("Models are stutter equivalent!")
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
)
from simasm.experimenter.transformer import (
    ExperimentParser,
    VerificationParser,
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
    # Parsers
    'ExperimentParser',
    'VerificationParser',
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
]
