"""
verification/ts.py

Transition system wrapper for ASM execution.

This module provides:
- TransitionSystemConfig: Configuration for TS construction
- TransitionSystem: Wraps a Stepper with labeling to produce observable traces

A transition system TS = (S, Act, ->, I, AP, L) where:
- S: Set of ASM states (implicit, generated on demand)
- Act: {main_rule} - the single action is firing the main rule
- ->: Transition relation via stepper.step()
- I: Initial state from stepper
- AP: Labels from labeling function
- L: Labeling function mapping states to label sets

The TransitionSystem tracks:
- Current state and label
- Full trace of label sets
- Step count for debugging

References:
- Definition (Transition System of ASM) in thesis
- Baier & Katoen, Principles of Model Checking, Definition 2.1
"""

from dataclasses import dataclass, field
from typing import Optional, List, Callable

from simasm.core.state import ASMState
from simasm.runtime.stepper import Stepper
from simasm.log.logger import get_logger
from .label import LabelingFunction, LabelSet
from .trace import Trace

logger = get_logger(__name__)


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class TransitionSystemConfig:
    """
    Configuration for transition system construction.
    
    Attributes:
        max_stutter_depth: Maximum consecutive stutter steps before warning
                          (for Assumption 2 - Finite Stutter Depth)
        record_trace: Whether to record full trace (memory intensive for long runs)
        record_states: Whether to record full state copies (very memory intensive)
    """
    max_stutter_depth: int = 1000
    record_trace: bool = True
    record_states: bool = False


# ============================================================================
# Transition System
# ============================================================================

class TransitionSystem:
    """
    Transition system TS = (S, Act, ->, I, AP, L) for an ASM.
    
    Wraps an ASM stepper with a labeling function to produce
    observable traces. Corresponds to Definition (TS of ASM).
    
    The transition system:
    - S: Set of ASM states (implicit, generated on demand via step())
    - Act: {P_M} where P_M is the main rule
    - ->: Transition relation via stepper.step()
    - I: Initial state from stepper
    - AP: Labels from labeling function (all defined labels)
    - L: S -> 2^AP labeling function
    
    Usage:
        # Create components
        stepper = ASMStepper(state, main_rule, evaluator)
        labeling = LabelingFunction()
        labeling.define("QueueEmpty", lambda s: s.get_var("queue_len") == 0)
        
        # Create transition system
        ts = TransitionSystem(stepper, labeling)
        
        # Execute and observe
        while ts.can_step():
            ts.step()
            print(f"Label: {ts.current_label}")
        
        # Get trace
        trace = ts.trace
    """
    
    def __init__(
        self,
        stepper: Stepper,
        labeling: LabelingFunction,
        config: Optional[TransitionSystemConfig] = None
    ):
        """
        Initialize transition system.
        
        Args:
            stepper: ASM stepper for state transitions
            labeling: Labeling function for atomic propositions
            config: Optional configuration
        """
        self._stepper = stepper
        self._labeling = labeling
        self._config = config or TransitionSystemConfig()
        
        # Initialize trace with initial label
        self._trace = Trace()
        self._initial_label = self._labeling.evaluate(self._stepper.current_state())
        self._trace.append(self._initial_label)
        
        # Track current label for efficient access
        self._current_label = self._initial_label
        
        # State history (optional)
        self._state_history: List[ASMState] = []
        if self._config.record_states:
            self._state_history.append(self._stepper.current_state().copy())
        
        # Stutter tracking (for Assumption 2 verification)
        self._consecutive_stutters = 0
        self._max_stutters_seen = 0
        
        logger.debug(f"Created TransitionSystem with initial label {self._initial_label}")
    
    @property
    def current_state(self) -> ASMState:
        """Current ASM state."""
        return self._stepper.current_state()
    
    @property
    def current_label(self) -> LabelSet:
        """L(current_state) - labels that hold in current state."""
        return self._current_label
    
    @property
    def initial_label(self) -> LabelSet:
        """Label of initial state (for Assumption 1 verification)."""
        return self._initial_label
    
    @property
    def step_count(self) -> int:
        """Number of transitions taken."""
        return self._stepper.step_count
    
    @property
    def sim_time(self) -> float:
        """Current simulation time."""
        return self._stepper.sim_time
    
    def step(self) -> bool:
        """
        Execute one transition (fire main rule).
        
        Updates the current state, computes new label, and extends trace.
        
        Returns:
            True if transition was taken, False if terminated
        """
        if not self.can_step():
            return False
        
        # Store previous label for stutter detection
        prev_label = self._current_label
        
        # Execute step
        result = self._stepper.step()
        if not result:
            return False
        
        # Compute new label
        self._current_label = self._labeling.evaluate(self._stepper.current_state())
        
        # Record trace
        if self._config.record_trace:
            self._trace.append(self._current_label)
        
        # Record state (if configured)
        if self._config.record_states:
            self._state_history.append(self._stepper.current_state().copy())
        
        # Track stuttering
        if self._current_label == prev_label:
            self._consecutive_stutters += 1
            self._max_stutters_seen = max(self._max_stutters_seen, self._consecutive_stutters)
            
            if self._consecutive_stutters >= self._config.max_stutter_depth:
                logger.warning(
                    f"Stutter depth {self._consecutive_stutters} reached at step {self.step_count}. "
                    f"Possible Assumption 2 violation (infinite stuttering)."
                )
        else:
            self._consecutive_stutters = 0
        
        return True
    
    def can_step(self) -> bool:
        """Check if another transition is possible (Assumption 3 check)."""
        return self._stepper.can_step()
    
    @property
    def trace(self) -> Trace:
        """
        Full trace from initial state to current state.
        
        Returns a copy to prevent external modification.
        """
        return self._trace.copy()
    
    @property 
    def trace_length(self) -> int:
        """Length of trace (number of states visited)."""
        return len(self._trace)
    
    def reset(self) -> None:
        """
        Reset to initial state for fresh verification run.
        
        Note: This requires the stepper to support reset.
        Currently, we recreate the trace from current state.
        
        Raises:
            NotImplementedError: If stepper doesn't support reset
        """
        # Check if stepper has reset method
        if hasattr(self._stepper, 'reset'):
            self._stepper.reset()
        else:
            raise NotImplementedError(
                "Stepper does not support reset. "
                "Create a new TransitionSystem instead."
            )
        
        # Reset trace
        self._trace = Trace()
        self._initial_label = self._labeling.evaluate(self._stepper.current_state())
        self._trace.append(self._initial_label)
        self._current_label = self._initial_label
        
        # Reset state history
        self._state_history = []
        if self._config.record_states:
            self._state_history.append(self._stepper.current_state().copy())
        
        # Reset stutter tracking
        self._consecutive_stutters = 0
        
        logger.debug("TransitionSystem reset to initial state")
    
    def run(self, max_steps: Optional[int] = None) -> int:
        """
        Run until can_step() returns False or max_steps reached.
        
        Args:
            max_steps: Maximum steps to take (None = unlimited)
        
        Returns:
            Number of steps taken
        """
        steps = 0
        while self.can_step():
            if max_steps is not None and steps >= max_steps:
                break
            self.step()
            steps += 1
        return steps
    
    def run_until_label_change(self, max_steps: int = 1000) -> int:
        """
        Run until label changes or max_steps reached.
        
        Useful for detecting when stutter phase ends.
        
        Args:
            max_steps: Maximum steps to try
        
        Returns:
            Number of steps taken (0 if label changed immediately)
        """
        initial_label = self._current_label
        steps = 0
        
        while self.can_step() and steps < max_steps:
            self.step()
            steps += 1
            if self._current_label != initial_label:
                break
        
        return steps
    
    @property
    def labeling(self) -> LabelingFunction:
        """The labeling function."""
        return self._labeling
    
    @property
    def labels(self) -> LabelSet:
        """All defined atomic propositions (AP)."""
        return frozenset(self._labeling.labels)
    
    @property
    def max_stutters_observed(self) -> int:
        """Maximum consecutive stutters observed (for debugging)."""
        return self._max_stutters_seen
    
    @property
    def state_history(self) -> List[ASMState]:
        """
        Full state history (if record_states was enabled).
        
        Returns copies to prevent modification.
        """
        return [s.copy() for s in self._state_history]
    
    def is_stutter_step(self) -> bool:
        """
        Check if the last step was a stutter step.
        
        A stutter step is one where the label didn't change.
        """
        if len(self._trace) < 2:
            return False
        return self._trace[-1] == self._trace[-2]
    
    def __repr__(self) -> str:
        return (
            f"TransitionSystem(steps={self.step_count}, "
            f"trace_len={len(self._trace)}, "
            f"labels={len(self._labeling)})"
        )
    
    def __str__(self) -> str:
        return (
            f"TransitionSystem:\n"
            f"  Steps: {self.step_count}\n"
            f"  Trace length: {len(self._trace)}\n"
            f"  Current label: {self._current_label}\n"
            f"  Labels defined: {self._labeling.label_names}"
        )


# ============================================================================
# Factory Functions
# ============================================================================

def create_transition_system(
    stepper: Stepper,
    labeling: LabelingFunction,
    record_trace: bool = True,
    record_states: bool = False,
    max_stutter_depth: int = 1000
) -> TransitionSystem:
    """
    Factory function to create a TransitionSystem.
    
    Args:
        stepper: ASM stepper for execution
        labeling: Labeling function
        record_trace: Whether to record trace
        record_states: Whether to record state copies
        max_stutter_depth: Warning threshold for consecutive stutters
    
    Returns:
        Configured TransitionSystem
    """
    config = TransitionSystemConfig(
        max_stutter_depth=max_stutter_depth,
        record_trace=record_trace,
        record_states=record_states
    )
    return TransitionSystem(stepper, labeling, config)


# ============================================================================
# Comparison Utilities
# ============================================================================

def initial_labels_match(ts_a: TransitionSystem, ts_b: TransitionSystem) -> bool:
    """
    Check Assumption 1: Initial state correspondence.
    
    Returns True if L_A(A₀) = L_B(B₀).
    
    Args:
        ts_a: First transition system
        ts_b: Second transition system
    
    Returns:
        True if initial labels match
    """
    return ts_a.initial_label == ts_b.initial_label


def current_labels_match(ts_a: TransitionSystem, ts_b: TransitionSystem) -> bool:
    """
    Check if current labels of two transition systems match.
    
    Args:
        ts_a: First transition system
        ts_b: Second transition system
    
    Returns:
        True if L_A(A) = L_B(B)
    """
    return ts_a.current_label == ts_b.current_label
