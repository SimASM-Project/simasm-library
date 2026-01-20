"""
verification/product.py

Augmented product transition system (Definition 9-10).

This module provides:
- ProductState: Triple (A, B, phase) representing a product state
- ProductTransitionSystem: Product construction with R1-R11 rules

The product construction is the key mechanism for verifying stutter
equivalence between two transition systems. The safety invariant
P(A, B, phase) ≡ (phase ≠ ERROR) characterizes stutter equivalence:
- If P holds for all reachable states, the systems are stutter equivalent
- If P is violated (ERROR reached), the systems are NOT stutter equivalent

Transition Rules (Definition 10):

From Sync (both at label Q, both systems step):
- R1: Both stutter (stay at Q) -> Sync
- R2: Both non-stutter to same Q' -> Sync
- R3: A to Q', B stutters -> ALeads(Q')
- R4: A stutters, B to Q' -> BLeads(Q')
- R5: Both non-stutter to different labels -> Error

From ALeads(Q') (A frozen, only B steps):
- R6: B stutters at Q -> ALeads(Q')
- R7: B reaches Q' -> Sync
- R8: B to other label Q'' not in {Q, Q'} -> Error

From BLeads(Q') (B frozen, only A steps):
- R9: A stutters at Q -> BLeads(Q')
- R10: A reaches Q' -> Sync
- R11: A to other label Q'' not in {Q, Q'} -> Error

From Error: No transitions (sink state).

References:
- Definition 8 (Phase) in thesis
- Definition 9 (Product Transition System) in thesis
- Definition 10 (Transition Rules R1-R11) in thesis
- Theorem 1 (Soundness of Product Construction) in thesis
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from copy import deepcopy

from simasm.core.state import ASMState
from simasm.log.logger import get_logger
from .ts import TransitionSystem
from .phase import (
    Phase, PhaseType, Sync, ALeads, BLeads, Error,
    SYNC, make_a_leads, make_b_leads,
    make_error_r5, make_error_r8, make_error_r11,
    is_error, is_sync, is_a_leads, is_b_leads,
    get_target_label, get_previous_label
)
from .label import LabelSet, format_label_set
from .trace import Trace

logger = get_logger(__name__)


# ============================================================================
# ProductState - Triple (A, B, phase)
# ============================================================================

@dataclass
class ProductState:
    """
    State in the product transition system.
    
    A product state is a triple (A, B, phase) where:
    - A is the current state of system A
    - B is the current state of system B
    - phase tracks synchronization status (Sync, ALeads, BLeads, or Error)
    
    Additionally stores:
    - label_a: L_A(A) for efficient access
    - label_b: L_B(B) for efficient access
    - step_number: Position in product path
    
    Invariants:
    - In Sync: label_a == label_b (both at same label Q)
    - In ALeads(Q'): label_a == Q' (target), label_b == Q (previous)
    - In BLeads(Q'): label_b == Q' (target), label_a == Q (previous)
    - In Error: Systems have diverged irrecoverably
    
    Usage:
        state = ProductState(
            state_a=ts_a.current_state,
            state_b=ts_b.current_state,
            phase=SYNC,
            label_a=labeling.evaluate(ts_a.current_state),
            label_b=labeling.evaluate(ts_b.current_state),
            step_number=0
        )
    """
    state_a: ASMState
    state_b: ASMState
    phase: Phase
    label_a: LabelSet
    label_b: LabelSet
    step_number: int = 0
    
    def copy(self) -> 'ProductState':
        """
        Create a deep copy of this product state.
        
        Returns:
            New ProductState with copied ASM states
        """
        return ProductState(
            state_a=self.state_a.copy(),
            state_b=self.state_b.copy(),
            phase=self.phase,  # Phases are immutable (frozen dataclasses)
            label_a=self.label_a,  # LabelSets are immutable (frozensets)
            label_b=self.label_b,
            step_number=self.step_number
        )
    
    def __repr__(self) -> str:
        la = format_label_set(self.label_a)
        lb = format_label_set(self.label_b)
        return f"ProductState(step={self.step_number}, A={la}, B={lb}, phase={self.phase})"
    
    def __str__(self) -> str:
        la = format_label_set(self.label_a)
        lb = format_label_set(self.label_b)
        return f"({la}, {lb}, {self.phase})"


# ============================================================================
# ProductTransitionSystem - Definition 9
# ============================================================================

class ProductTransitionSystem:
    """
    Augmented product of two transition systems (Definition 9).
    
    Implements the product construction with phase tracking and
    transition rules R1-R11 for stutter equivalence verification.
    
    Product system: TS_× = (S_×, Act_×, ->_×, I_×, AP_×, L_×) where:
    - S_× = S_A × S_B × Phase
    - I_× = {(A₀, B₀, sync) | A₀ ∈ I_A, B₀ ∈ I_B, L_A(A₀) = L_B(B₀)}
    - ->_× defined by rules R1-R11 based on current phase
    - AP_× = AP (shared atomic propositions)
    - L_× maps product states to (phase, labels)
    
    The safety invariant P(A, B, phase) ≡ (phase ≠ ERROR).
    By Theorem 1, if P holds for all reachable states, the systems
    are stutter equivalent.
    
    Usage:
        # Create transition systems
        ts_a = TransitionSystem(stepper_a, labeling)
        ts_b = TransitionSystem(stepper_b, labeling)
        
        # Create product system
        product = ProductTransitionSystem(ts_a, ts_b)
        
        # Execute and verify
        while product.can_step():
            product.step()
            if product.is_error():
                print("Systems diverged!")
                break
        else:
            print("Systems are stutter equivalent")
    
    Thread Safety:
        Not thread-safe. Use separate instances for concurrent verification.
    """
    
    def __init__(self, ts_a: TransitionSystem, ts_b: TransitionSystem):
        """
        Initialize product system.
        
        Verifies Assumption 1 (initial state correspondence):
        L_A(A₀) = L_B(B₀) must hold.
        
        Args:
            ts_a: First transition system (system A)
            ts_b: Second transition system (system B)
            
        Raises:
            ValueError: If initial labels don't match (Assumption 1 violation)
        """
        self._ts_a = ts_a
        self._ts_b = ts_b
        
        # Verify Assumption 1: Initial state correspondence
        initial_label_a = ts_a.initial_label
        initial_label_b = ts_b.initial_label
        
        if initial_label_a != initial_label_b:
            raise ValueError(
                f"Assumption 1 violation: Initial labels don't match. "
                f"L_A(A_0) = {format_label_set(initial_label_a)}, "
                f"L_B(B_0) = {format_label_set(initial_label_b)}"
            )
        
        # Initialize phase to Sync (Definition 9)
        self._phase: Phase = SYNC
        
        # Track step count
        self._step_count: int = 0
        
        # Record path for counterexample generation
        self._path: List[ProductState] = []
        
        # Record initial state
        initial_state = ProductState(
            state_a=ts_a.current_state.copy(),
            state_b=ts_b.current_state.copy(),
            phase=SYNC,
            label_a=initial_label_a,
            label_b=initial_label_b,
            step_number=0
        )
        self._path.append(initial_state)
        
        # Track projection traces (Definition 13)
        self._trace_a = Trace()
        self._trace_a.append(initial_label_a)
        
        self._trace_b = Trace()
        self._trace_b.append(initial_label_b)
        
        # Last applied rule for debugging
        self._last_rule: str = "INIT"
        
        logger.debug(
            f"Created ProductTransitionSystem with initial label "
            f"{format_label_set(initial_label_a)}"
        )
    
    # ========================================================================
    # Properties
    # ========================================================================
    
    @property
    def current_state(self) -> ProductState:
        """
        Current product state (A, B, phase).
        
        Returns a copy to prevent external modification.
        """
        return ProductState(
            state_a=self._ts_a.current_state.copy(),
            state_b=self._ts_b.current_state.copy(),
            phase=self._phase,
            label_a=self._ts_a.current_label,
            label_b=self._ts_b.current_label,
            step_number=self._step_count
        )
    
    @property
    def phase(self) -> Phase:
        """Current synchronization phase."""
        return self._phase
    
    @property
    def label_a(self) -> LabelSet:
        """Current label of system A: L_A(A)."""
        return self._ts_a.current_label
    
    @property
    def label_b(self) -> LabelSet:
        """Current label of system B: L_B(B)."""
        return self._ts_b.current_label
    
    @property
    def step_count(self) -> int:
        """Number of product transitions taken."""
        return self._step_count
    
    @property
    def last_rule(self) -> str:
        """Name of the last rule applied (for debugging)."""
        return self._last_rule
    
    # ========================================================================
    # State Checks
    # ========================================================================
    
    def is_error(self) -> bool:
        """Check if current phase is Error."""
        return is_error(self._phase)
    
    def is_sync(self) -> bool:
        """Check if current phase is Sync."""
        return is_sync(self._phase)
    
    def is_a_leads(self) -> bool:
        """Check if current phase is ALeads."""
        return is_a_leads(self._phase)
    
    def is_b_leads(self) -> bool:
        """Check if current phase is BLeads."""
        return is_b_leads(self._phase)
    
    def can_step(self) -> bool:
        """
        Check if product can take another step.
        
        Returns False if:
        - In Error state (sink)
        - Both underlying systems have terminated (when in Sync)
        - The active system has terminated (when in ALeads/BLeads)
        """
        if is_error(self._phase):
            return False
        
        if is_sync(self._phase):
            # In Sync, both systems step, so both must be able to step
            return self._ts_a.can_step() and self._ts_b.can_step()
        elif is_a_leads(self._phase):
            # In ALeads, only B steps
            return self._ts_b.can_step()
        elif is_b_leads(self._phase):
            # In BLeads, only A steps
            return self._ts_a.can_step()
        
        return False
    
    # ========================================================================
    # Transition Execution
    # ========================================================================
    
    def step(self) -> Phase:
        """
        Execute one product transition using rules R1-R11.
        
        Transition behavior depends on current phase:
        
        **From Sync (both at label Q):** Both systems step.
        - R1: Both stutter (stay at Q) -> Sync
        - R2: Both non-stutter to same Q' -> Sync
        - R3: A to Q', B stutters -> ALeads(Q')
        - R4: A stutters, B to Q' -> BLeads(Q')
        - R5: Both non-stutter to different labels -> Error
        
        **From ALeads(Q'):** A is frozen, only B steps.
        - R6: B stutters at Q -> ALeads(Q')
        - R7: B reaches Q' -> Sync
        - R8: B to other label -> Error
        
        **From BLeads(Q'):** B is frozen, only A steps.
        - R9: A stutters at Q -> BLeads(Q')
        - R10: A reaches Q' -> Sync
        - R11: A to other label -> Error
        
        **From Error:** No transitions (sink state).
        
        Returns:
            The new phase after transition
            
        Raises:
            RuntimeError: If in Error state (no transitions possible)
            RuntimeError: If underlying system cannot step when required
        """
        if is_error(self._phase):
            raise RuntimeError("Cannot step from Error state (sink)")
        
        if not self.can_step():
            raise RuntimeError("Cannot step: underlying system(s) terminated")
        
        # Dispatch based on current phase
        if is_sync(self._phase):
            new_phase = self._apply_sync_rules()
        elif is_a_leads(self._phase):
            target = get_target_label(self._phase)
            previous = get_previous_label(self._phase)
            new_phase = self._apply_a_leads_rules(target, previous)
        elif is_b_leads(self._phase):
            target = get_target_label(self._phase)
            previous = get_previous_label(self._phase)
            new_phase = self._apply_b_leads_rules(target, previous)
        else:
            raise RuntimeError(f"Unknown phase type: {self._phase}")
        
        # Update phase
        self._phase = new_phase
        self._step_count += 1
        
        # Record new state in path
        new_state = ProductState(
            state_a=self._ts_a.current_state.copy(),
            state_b=self._ts_b.current_state.copy(),
            phase=new_phase,
            label_a=self._ts_a.current_label,
            label_b=self._ts_b.current_label,
            step_number=self._step_count
        )
        self._path.append(new_state)
        
        logger.debug(
            f"Step {self._step_count}: {self._last_rule} -> {new_phase}"
        )
        
        return new_phase
    
    def _apply_sync_rules(self) -> Phase:
        """
        Apply rules R1-R5 from Sync phase.
        
        Both systems step. The rule applied depends on whether
        each system takes a stutter step (label unchanged) or
        non-stutter step (label changes).
        
        Returns:
            New phase after transition
        """
        # Store current labels before stepping
        old_label_a = self._ts_a.current_label
        old_label_b = self._ts_b.current_label
        
        # Both systems step
        self._ts_a.step()
        self._ts_b.step()
        
        # Get new labels
        new_label_a = self._ts_a.current_label
        new_label_b = self._ts_b.current_label
        
        # Record in projection traces
        self._trace_a.append(new_label_a)
        self._trace_b.append(new_label_b)
        
        # Determine stutter status
        a_stutters = (new_label_a == old_label_a)
        b_stutters = (new_label_b == old_label_b)
        
        # Apply appropriate rule
        if a_stutters and b_stutters:
            # R1: Both stutter (stay at Q) -> Sync
            self._last_rule = "R1"
            return SYNC
        
        elif not a_stutters and not b_stutters:
            # Both non-stutter
            if new_label_a == new_label_b:
                # R2: Both non-stutter to same Q' -> Sync
                self._last_rule = "R2"
                return SYNC
            else:
                # R5: Both non-stutter to different labels -> Error
                self._last_rule = "R5"
                return make_error_r5(self._step_count + 1, new_label_a, new_label_b)
        
        elif not a_stutters and b_stutters:
            # R3: A to Q', B stutters -> ALeads(Q')
            self._last_rule = "R3"
            return make_a_leads(target=new_label_a, previous=old_label_a)
        
        else:  # a_stutters and not b_stutters
            # R4: A stutters, B to Q' -> BLeads(Q')
            self._last_rule = "R4"
            return make_b_leads(target=new_label_b, previous=old_label_b)
    
    def _apply_a_leads_rules(self, target: LabelSet, previous: LabelSet) -> Phase:
        """
        Apply rules R6-R8 from ALeads phase.
        
        A is frozen at target label Q'. Only B steps.
        B must catch up from previous label Q to target Q'.
        
        Args:
            target: Q' that A has reached (A is frozen here)
            previous: Q that B is still at
        
        Returns:
            New phase after transition
        """
        # Store B's current label before stepping
        old_label_b = self._ts_b.current_label
        
        # Only B steps (A is frozen)
        self._ts_b.step()
        
        # Get B's new label
        new_label_b = self._ts_b.current_label
        
        # Record in B's projection trace (A is frozen, so no change to trace_a)
        self._trace_b.append(new_label_b)
        
        # Determine which rule applies
        if new_label_b == previous:
            # R6: B stutters at Q -> ALeads(Q')
            self._last_rule = "R6"
            return ALeads(target_label=target, previous_label=previous)
        
        elif new_label_b == target:
            # R7: B reaches Q' -> Sync
            self._last_rule = "R7"
            return SYNC
        
        else:
            # R8: B to other label Q'' not in {Q, Q'} -> Error
            self._last_rule = "R8"
            return make_error_r8(self._step_count + 1, target, previous, new_label_b)
    
    def _apply_b_leads_rules(self, target: LabelSet, previous: LabelSet) -> Phase:
        """
        Apply rules R9-R11 from BLeads phase.
        
        B is frozen at target label Q'. Only A steps.
        A must catch up from previous label Q to target Q'.
        
        Args:
            target: Q' that B has reached (B is frozen here)
            previous: Q that A is still at
        
        Returns:
            New phase after transition
        """
        # Store A's current label before stepping
        old_label_a = self._ts_a.current_label
        
        # Only A steps (B is frozen)
        self._ts_a.step()
        
        # Get A's new label
        new_label_a = self._ts_a.current_label
        
        # Record in A's projection trace (B is frozen, so no change to trace_b)
        self._trace_a.append(new_label_a)
        
        # Determine which rule applies
        if new_label_a == previous:
            # R9: A stutters at Q -> BLeads(Q')
            self._last_rule = "R9"
            return BLeads(target_label=target, previous_label=previous)
        
        elif new_label_a == target:
            # R10: A reaches Q' -> Sync
            self._last_rule = "R10"
            return SYNC
        
        else:
            # R11: A to other label Q'' not in {Q, Q'} -> Error
            self._last_rule = "R11"
            return make_error_r11(self._step_count + 1, target, previous, new_label_a)
    
    # ========================================================================
    # Trace Access (Definition 13)
    # ========================================================================
    
    @property
    def trace_a(self) -> Trace:
        """
        A-projection trace: trace_A(π_×) (Definition 13).
        
        The sequence L_A(A₀) -> L_A(A₁) -> ... -> L_A(A_n)
        where A_i is the A-component at step i of the product path.
        
        Note: When A is frozen (in ALeads phase), consecutive
        entries in trace_a will be identical (stutter steps from A's view).
        
        Returns:
            Copy of A's projection trace
        """
        return self._trace_a.copy()
    
    @property
    def trace_b(self) -> Trace:
        """
        B-projection trace: trace_B(π_×) (Definition 13).
        
        The sequence L_B(B₀) -> L_B(B₁) -> ... -> L_B(B_n)
        where B_i is the B-component at step i of the product path.
        
        Note: When B is frozen (in BLeads phase), consecutive
        entries in trace_b will be identical (stutter steps from B's view).
        
        Returns:
            Copy of B's projection trace
        """
        return self._trace_b.copy()
    
    @property
    def path(self) -> List[ProductState]:
        """
        Full product path traversed so far.
        
        Returns copies of all states to prevent external modification.
        Used for counterexample generation when ERROR is reached.
        
        Returns:
            List of ProductState copies from initial to current
        """
        return [s.copy() for s in self._path]
    
    # ========================================================================
    # Reset
    # ========================================================================
    
    def reset(self) -> None:
        """
        Reset to initial state for fresh verification.
        
        Note: This requires the underlying steppers to support reset.
        
        Raises:
            NotImplementedError: If steppers don't support reset
        """
        # Reset underlying transition systems
        self._ts_a.reset()
        self._ts_b.reset()
        
        # Reset phase and step count
        self._phase = SYNC
        self._step_count = 0
        
        # Reset path
        initial_state = ProductState(
            state_a=self._ts_a.current_state.copy(),
            state_b=self._ts_b.current_state.copy(),
            phase=SYNC,
            label_a=self._ts_a.initial_label,
            label_b=self._ts_b.initial_label,
            step_number=0
        )
        self._path = [initial_state]
        
        # Reset traces
        self._trace_a = Trace()
        self._trace_a.append(self._ts_a.initial_label)
        
        self._trace_b = Trace()
        self._trace_b.append(self._ts_b.initial_label)
        
        self._last_rule = "INIT"
        
        logger.debug("ProductTransitionSystem reset to initial state")
    
    # ========================================================================
    # Execution Helpers
    # ========================================================================
    
    def run(self, max_steps: Optional[int] = None) -> Tuple[bool, int]:
        """
        Run until error, termination, or max_steps reached.
        
        Args:
            max_steps: Maximum steps to take (None = unlimited)
        
        Returns:
            Tuple of (reached_error, steps_taken)
        """
        steps = 0
        while self.can_step():
            if max_steps is not None and steps >= max_steps:
                break
            self.step()
            steps += 1
            if self.is_error():
                return (True, steps)
        return (False, steps)
    
    def verify(self, max_steps: Optional[int] = None) -> bool:
        """
        Verify stutter equivalence up to max_steps.
        
        Args:
            max_steps: Maximum steps to explore
        
        Returns:
            True if no error found (systems are stutter equivalent
            up to the explored depth)
        """
        reached_error, _ = self.run(max_steps)
        return not reached_error
    
    # ========================================================================
    # Diagnostics
    # ========================================================================
    
    def get_error_info(self) -> Optional[Error]:
        """
        Get error information if in Error state.
        
        Returns:
            Error phase with diagnostic info, or None if not in Error
        """
        if is_error(self._phase):
            return self._phase
        return None
    
    def get_counterexample(self) -> Optional[List[ProductState]]:
        """
        Get counterexample path if in Error state.
        
        The counterexample is the path from initial state to the
        Error state, demonstrating that the systems diverge.
        
        Returns:
            Path to error state, or None if not in Error
        """
        if is_error(self._phase):
            return self.path
        return None
    
    def __repr__(self) -> str:
        return (
            f"ProductTransitionSystem(steps={self._step_count}, "
            f"phase={self._phase}, last_rule={self._last_rule})"
        )
    
    def __str__(self) -> str:
        la = format_label_set(self.label_a)
        lb = format_label_set(self.label_b)
        return (
            f"ProductTransitionSystem:\n"
            f"  Steps: {self._step_count}\n"
            f"  Phase: {self._phase}\n"
            f"  Label A: {la}\n"
            f"  Label B: {lb}\n"
            f"  Last rule: {self._last_rule}"
        )


# ============================================================================
# Factory Functions
# ============================================================================

def create_product_system(
    ts_a: TransitionSystem,
    ts_b: TransitionSystem
) -> ProductTransitionSystem:
    """
    Factory function to create a ProductTransitionSystem.
    
    Args:
        ts_a: First transition system
        ts_b: Second transition system
    
    Returns:
        Configured ProductTransitionSystem
    
    Raises:
        ValueError: If initial labels don't match
    """
    return ProductTransitionSystem(ts_a, ts_b)


# ============================================================================
# Verification Utilities
# ============================================================================

def verify_stutter_equivalence(
    ts_a: TransitionSystem,
    ts_b: TransitionSystem,
    max_steps: Optional[int] = None
) -> Tuple[bool, Optional[List[ProductState]]]:
    """
    One-shot stutter equivalence verification.
    
    Creates a product system and runs verification, returning
    the result and any counterexample.
    
    Args:
        ts_a: First transition system
        ts_b: Second transition system
        max_steps: Maximum steps to explore
    
    Returns:
        Tuple of:
        - bool: True if systems are stutter equivalent (up to max_steps)
        - Optional counterexample path if error found
    
    Raises:
        ValueError: If initial labels don't match
    """
    product = ProductTransitionSystem(ts_a, ts_b)
    is_equivalent = product.verify(max_steps)
    counterexample = product.get_counterexample() if not is_equivalent else None
    return (is_equivalent, counterexample)