"""
verification/phase.py

Synchronization phases for product transition system (Definition 8).

This module provides the Phase dataclasses that track synchronization
status between two transition systems in the product construction:

- Sync: Both systems are synchronized with matching labels
- ALeads: System A has moved ahead, waiting for B to catch up
- BLeads: System B has moved ahead, waiting for A to catch up  
- Error: Irrecoverable divergence detected

The phase component is critical for the stutter equivalence verification:
- The safety invariant P(A, B, phase) ≡ (phase ≠ ERROR)
- If P holds for all reachable states, the systems are stutter equivalent

References:
- Definition 8 (Phase) in thesis
- Definition 9-10 (Product Transition System) in thesis
- Rules R1-R11 for phase transitions
"""

from dataclasses import dataclass
from typing import Optional, Union
from enum import Enum, auto

from simasm.log.logger import get_logger
from .label import LabelSet, format_label_set

logger = get_logger(__name__)


# ============================================================================
# Phase Type Enum (for quick type checking)
# ============================================================================

class PhaseType(Enum):
    """Enumeration of phase types for efficient dispatch."""
    SYNC = auto()
    A_LEADS = auto()
    B_LEADS = auto()
    ERROR = auto()


# ============================================================================
# Phase Base Class
# ============================================================================

class Phase:
    """
    Base class for synchronization phases.
    
    The phase tracks synchronization status between two transition systems
    in the product construction (Definition 8).
    
    Phase values:
    - Sync: Both systems synchronized at same label Q
    - ALeads(Q'): A at Q', B at Q ≠ Q', A frozen waiting for B
    - BLeads(Q'): B at Q', A at Q ≠ Q', B frozen waiting for A
    - Error: Irrecoverable divergence (sink state)
    
    The phase determines which transition rules apply:
    - From Sync: Rules R1-R5 (both systems step)
    - From ALeads: Rules R6-R8 (only B steps)
    - From BLeads: Rules R9-R11 (only A steps)
    - From Error: No transitions (sink)
    """
    
    @property
    def phase_type(self) -> PhaseType:
        """Return the phase type enum for efficient dispatch."""
        raise NotImplementedError
    
    def is_sync(self) -> bool:
        """Check if phase is Sync."""
        return False
    
    def is_a_leads(self) -> bool:
        """Check if A is leading (frozen)."""
        return False
    
    def is_b_leads(self) -> bool:
        """Check if B is leading (frozen)."""
        return False
    
    def is_leading(self) -> bool:
        """Check if either system is leading."""
        return self.is_a_leads() or self.is_b_leads()
    
    def is_error(self) -> bool:
        """Check if phase is Error."""
        return False


# ============================================================================
# Sync Phase
# ============================================================================

@dataclass(frozen=True)
class Sync(Phase):
    """
    Both systems are synchronized with matching labels.
    
    Precondition: L_A(A) = L_B(B) = Q for some Q ∈ 2^AP
    
    From Sync, both systems step together using Rules R1-R5:
    - R1: Both stutter (stay at Q) -> Sync
    - R2: Both non-stutter to same Q' -> Sync  
    - R3: A to Q', B stutters -> ALeads(Q')
    - R4: A stutters, B to Q' -> BLeads(Q')
    - R5: Both non-stutter to different labels -> Error
    
    Note: Sync does not store the common label Q because it can be
    computed from the current states: Q = L_A(A) = L_B(B).
    """
    
    @property
    def phase_type(self) -> PhaseType:
        return PhaseType.SYNC
    
    def is_sync(self) -> bool:
        return True
    
    def __repr__(self) -> str:
        return "Sync()"
    
    def __str__(self) -> str:
        return "sync"


# ============================================================================
# ALeads Phase
# ============================================================================

@dataclass(frozen=True)
class ALeads(Phase):
    """
    System A has moved to target_label, B is catching up.
    
    A is FROZEN at target_label (Q').
    B is still at previous_label (Q) and must catch up to Q'.
    
    Invariants:
    - L_A(A) = target_label = Q'
    - L_B(B) = previous_label = Q
    - Q ≠ Q'
    
    From ALeads(Q'), only B steps using Rules R6-R8:
    - R6: B stutters at Q -> ALeads(Q')
    - R7: B reaches Q' -> Sync
    - R8: B to other label Q'' not in {Q, Q'} -> Error
    
    Attributes:
        target_label: Q' that A has reached (A is frozen here)
        previous_label: Q that B is still at (B must catch up from here)
    """
    target_label: LabelSet
    previous_label: LabelSet
    
    @property
    def phase_type(self) -> PhaseType:
        return PhaseType.A_LEADS
    
    def is_a_leads(self) -> bool:
        return True
    
    def __repr__(self) -> str:
        target = format_label_set(self.target_label)
        prev = format_label_set(self.previous_label)
        return f"ALeads(target={target}, previous={prev})"
    
    def __str__(self) -> str:
        target = format_label_set(self.target_label)
        return f"A_leads({target})"


# ============================================================================
# BLeads Phase
# ============================================================================

@dataclass(frozen=True)
class BLeads(Phase):
    """
    System B has moved to target_label, A is catching up.
    
    B is FROZEN at target_label (Q').
    A is still at previous_label (Q) and must catch up to Q'.
    
    Invariants:
    - L_B(B) = target_label = Q'
    - L_A(A) = previous_label = Q
    - Q ≠ Q'
    
    From BLeads(Q'), only A steps using Rules R9-R11:
    - R9: A stutters at Q -> BLeads(Q')
    - R10: A reaches Q' -> Sync
    - R11: A to other label Q'' not in {Q, Q'} -> Error
    
    Attributes:
        target_label: Q' that B has reached (B is frozen here)
        previous_label: Q that A is still at (A must catch up from here)
    """
    target_label: LabelSet
    previous_label: LabelSet
    
    @property
    def phase_type(self) -> PhaseType:
        return PhaseType.B_LEADS
    
    def is_b_leads(self) -> bool:
        return True
    
    def __repr__(self) -> str:
        target = format_label_set(self.target_label)
        prev = format_label_set(self.previous_label)
        return f"BLeads(target={target}, previous={prev})"
    
    def __str__(self) -> str:
        target = format_label_set(self.target_label)
        return f"B_leads({target})"


# ============================================================================
# Error Phase
# ============================================================================

@dataclass(frozen=True)
class Error(Phase):
    """
    Irrecoverable divergence detected.
    
    The ERROR state is a sink with no outgoing transitions.
    Reaching ERROR means the systems are NOT stutter equivalent.
    
    This happens when:
    - R5: From Sync, both take non-stutter steps to different labels
    - R8: From ALeads(Q'), B transitions to Q'' not in {Q, Q'}
    - R11: From BLeads(Q'), A transitions to Q'' not in {Q, Q'}
    
    Attributes:
        reason: Human-readable explanation of why divergence occurred
        step_number: Step at which divergence was detected
        label_a: Label of system A when divergence occurred
        label_b: Label of system B when divergence occurred
        rule: Which rule caused the error (R5, R8, or R11)
    """
    reason: str = ""
    step_number: int = 0
    label_a: Optional[LabelSet] = None
    label_b: Optional[LabelSet] = None
    rule: str = ""
    
    @property
    def phase_type(self) -> PhaseType:
        return PhaseType.ERROR
    
    def is_error(self) -> bool:
        return True
    
    def __repr__(self) -> str:
        if self.reason:
            return f"Error(reason={self.reason!r}, step={self.step_number})"
        return f"Error(step={self.step_number})"
    
    def __str__(self) -> str:
        if self.reason:
            return f"ERROR: {self.reason}"
        return "ERROR"


# ============================================================================
# Phase Singleton
# ============================================================================

# Singleton Sync instance (since it has no state)
SYNC = Sync()


# ============================================================================
# Helper Functions
# ============================================================================

def is_sync(phase: Phase) -> bool:
    """Check if phase is Sync."""
    return phase.is_sync()


def is_a_leads(phase: Phase) -> bool:
    """Check if phase is ALeads."""
    return phase.is_a_leads()


def is_b_leads(phase: Phase) -> bool:
    """Check if phase is BLeads."""
    return phase.is_b_leads()


def is_leading(phase: Phase) -> bool:
    """Check if either system is leading."""
    return phase.is_leading()


def is_error(phase: Phase) -> bool:
    """Check if phase is Error."""
    return phase.is_error()


def get_target_label(phase: Phase) -> Optional[LabelSet]:
    """
    Get the target label for leading phases.
    
    Args:
        phase: Current phase
    
    Returns:
        Target label Q' if phase is ALeads or BLeads, None otherwise
    """
    if isinstance(phase, (ALeads, BLeads)):
        return phase.target_label
    return None


def get_previous_label(phase: Phase) -> Optional[LabelSet]:
    """
    Get the previous label for leading phases.
    
    Args:
        phase: Current phase
    
    Returns:
        Previous label Q if phase is ALeads or BLeads, None otherwise
    """
    if isinstance(phase, (ALeads, BLeads)):
        return phase.previous_label
    return None


def get_frozen_system(phase: Phase) -> Optional[str]:
    """
    Get which system is frozen in the current phase.
    
    Args:
        phase: Current phase
    
    Returns:
        "A" if A is frozen (ALeads), "B" if B is frozen (BLeads), None otherwise
    """
    if phase.is_a_leads():
        return "A"
    elif phase.is_b_leads():
        return "B"
    return None


def get_moving_system(phase: Phase) -> Optional[str]:
    """
    Get which system should move in the current phase.
    
    Args:
        phase: Current phase
    
    Returns:
        "B" if ALeads (only B moves)
        "A" if BLeads (only A moves)
        "both" if Sync (both move)
        None if Error (no moves)
    """
    if phase.is_sync():
        return "both"
    elif phase.is_a_leads():
        return "B"
    elif phase.is_b_leads():
        return "A"
    return None


# ============================================================================
# Phase Transition Helpers
# ============================================================================

def make_a_leads(target: LabelSet, previous: LabelSet) -> ALeads:
    """
    Create an ALeads phase.
    
    Called when A takes a non-stutter step to target while B stutters at previous.
    
    Args:
        target: Q' that A has reached
        previous: Q that B is still at
    
    Returns:
        ALeads phase
    """
    return ALeads(target_label=target, previous_label=previous)


def make_b_leads(target: LabelSet, previous: LabelSet) -> BLeads:
    """
    Create a BLeads phase.
    
    Called when B takes a non-stutter step to target while A stutters at previous.
    
    Args:
        target: Q' that B has reached
        previous: Q that A is still at
    
    Returns:
        BLeads phase
    """
    return BLeads(target_label=target, previous_label=previous)


def make_error(
    reason: str,
    step_number: int = 0,
    label_a: Optional[LabelSet] = None,
    label_b: Optional[LabelSet] = None,
    rule: str = ""
) -> Error:
    """
    Create an Error phase.
    
    Args:
        reason: Human-readable explanation
        step_number: Step at which divergence occurred
        label_a: Label of system A
        label_b: Label of system B
        rule: Which rule caused the error
    
    Returns:
        Error phase with diagnostic information
    """
    return Error(
        reason=reason,
        step_number=step_number,
        label_a=label_a,
        label_b=label_b,
        rule=rule
    )


def make_error_r5(
    step_number: int,
    label_a: LabelSet,
    label_b: LabelSet
) -> Error:
    """
    Create an Error for Rule R5 (divergence from Sync).
    
    Both systems took non-stutter steps to different labels.
    """
    return Error(
        reason=f"Both systems diverged: A->{format_label_set(label_a)}, B->{format_label_set(label_b)}",
        step_number=step_number,
        label_a=label_a,
        label_b=label_b,
        rule="R5"
    )


def make_error_r8(
    step_number: int,
    target: LabelSet,
    previous: LabelSet,
    actual: LabelSet
) -> Error:
    """
    Create an Error for Rule R8 (B diverges while A leads).
    
    B transitioned to a label that is neither previous nor target.
    """
    return Error(
        reason=f"B diverged: expected {format_label_set(previous)} or {format_label_set(target)}, got {format_label_set(actual)}",
        step_number=step_number,
        label_a=target,
        label_b=actual,
        rule="R8"
    )


def make_error_r11(
    step_number: int,
    target: LabelSet,
    previous: LabelSet,
    actual: LabelSet
) -> Error:
    """
    Create an Error for Rule R11 (A diverges while B leads).
    
    A transitioned to a label that is neither previous nor target.
    """
    return Error(
        reason=f"A diverged: expected {format_label_set(previous)} or {format_label_set(target)}, got {format_label_set(actual)}",
        step_number=step_number,
        label_a=actual,
        label_b=target,
        rule="R11"
    )