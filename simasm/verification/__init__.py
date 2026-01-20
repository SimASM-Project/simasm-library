"""
verification package

Stutter equivalence verification framework for SimASM.

This package provides tools for verifying stutter equivalence between
two Abstract State Machines using the product transition system
construction and k-induction algorithm.

Modules:
- label: Atomic propositions and labeling functions
- trace: Trace representation and stutter equivalence operations
- ts: Transition system wrapper for ASM
- phase: Synchronization phases for product system
- product: Augmented product transition system
- kinduction: K-induction verification algorithm

References:
- Thesis: Transition System of ASM Framework
- Thesis: Equivalence in Transition Systems of ASM
- Baier & Katoen, Principles of Model Checking
"""

from .label import (
    Label,
    LabelSet,
    LabelingFunction,
    empty_label_set,
    label_set,
    label_set_from_names,
    labels_equal,
    format_label_set,
)

from .trace import (
    Trace,
    no_stutter_trace,
    is_stutter_free,
    traces_stutter_equivalent,
    extend_no_stutter,
    is_prefix,
    common_prefix,
    trace_divergence_point,
    trace_from_labels,
    count_stutter_steps,
    stutter_ratio,
)

from .ts import (
    TransitionSystem,
    TransitionSystemConfig,
    create_transition_system,
    initial_labels_match,
    current_labels_match,
)

from .phase import (
    Phase,
    PhaseType,
    Sync,
    ALeads,
    BLeads,
    Error,
    SYNC,
    is_sync,
    is_a_leads,
    is_b_leads,
    is_leading,
    is_error,
    get_target_label,
    get_previous_label,
    get_frozen_system,
    get_moving_system,
    make_a_leads,
    make_b_leads,
    make_error,
)

from .product import (
    ProductState,
    ProductTransitionSystem,
    create_product_system,
    verify_stutter_equivalence,
)

from .kinduction import (
    VerificationStatus,
    VerificationResult,
    KInductionVerifier,
    verify_stutter_equivalence as kinduction_verify,
    quick_verify,
    format_verification_report,
    format_counterexample,
)

__all__ = [
    # label.py
    'Label',
    'LabelSet',
    'LabelingFunction',
    'empty_label_set',
    'label_set',
    'label_set_from_names',
    'labels_equal',
    'format_label_set',
    # trace.py
    'Trace',
    'no_stutter_trace',
    'is_stutter_free',
    'traces_stutter_equivalent',
    'extend_no_stutter',
    'is_prefix',
    'common_prefix',
    'trace_divergence_point',
    'trace_from_labels',
    'count_stutter_steps',
    'stutter_ratio',
    # ts.py
    'TransitionSystem',
    'TransitionSystemConfig',
    'create_transition_system',
    'initial_labels_match',
    'current_labels_match',
    # phase.py
    'Phase',
    'PhaseType',
    'Sync',
    'ALeads',
    'BLeads',
    'Error',
    'SYNC',
    'is_sync',
    'is_a_leads',
    'is_b_leads',
    'is_leading',
    'is_error',
    'get_target_label',
    'get_previous_label',
    'get_frozen_system',
    'get_moving_system',
    'make_a_leads',
    'make_b_leads',
    'make_error',
    # product.py
    'ProductState',
    'ProductTransitionSystem',
    'create_product_system',
    'verify_stutter_equivalence',
    # kinduction.py
    'VerificationStatus',
    'VerificationResult',
    'KInductionVerifier',
    'kinduction_verify',
    'quick_verify',
    'format_verification_report',
    'format_counterexample',
]
