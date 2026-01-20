"""
verification/kinduction.py

K-induction algorithm for stutter equivalence verification (Algorithm 1).

This module provides:
- VerificationStatus: Enum for verification outcomes
- VerificationResult: Detailed result of verification
- KInductionVerifier: Main verification algorithm

The k-induction algorithm verifies that ERROR is unreachable in the
product transition system, which implies stutter equivalence by Theorem 1.

Algorithm 1 (K-Induction for Stutter Equivalence):
1. Construct product system TS_×
2. Define safety invariant P(A, B, phase) ≡ (phase ≠ ERROR)
3. For k = 1 to k_max:
   a. Base case: Check all paths of length ≤k from initial states
   b. If ERROR found: return NOT_EQUIVALENT with counterexample
   c. Inductive step: Check if k consecutive non-ERROR states
      guarantee the next state is also non-ERROR
   d. If inductive step holds: return EQUIVALENT
4. Return UNKNOWN if k_max reached without conclusion

For deterministic systems (our case), this simplifies to bounded
model checking: explore up to k_max steps and check for ERROR.

References:
- Algorithm 1 (K-Induction) in thesis
- Theorem 1 (Soundness of Product Construction)
- Sheeran, Singh, Stålmarck: "Checking Safety Properties Using
  Induction and a SAT-Solver" (2000)
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Callable, Tuple
import time

from simasm.log.logger import get_logger
from .ts import TransitionSystem
from .product import ProductTransitionSystem, ProductState
from .phase import Phase, Error, is_error, is_sync

logger = get_logger(__name__)


# ============================================================================
# Verification Status
# ============================================================================

class VerificationStatus(Enum):
    """
    Result status of verification.
    
    Values:
        EQUIVALENT: Proved stutter equivalent (ERROR unreachable)
        NOT_EQUIVALENT: Found counterexample (ERROR reached)
        UNKNOWN: Inconclusive (k_max or timeout reached)
        TIMEOUT: Verification timed out
        ASSUMPTION_VIOLATED: Precondition failed (e.g., Assumption 1)
    """
    EQUIVALENT = auto()
    NOT_EQUIVALENT = auto()
    UNKNOWN = auto()
    TIMEOUT = auto()
    ASSUMPTION_VIOLATED = auto()


# ============================================================================
# Verification Result
# ============================================================================

@dataclass
class VerificationResult:
    """
    Result of k-induction verification.
    
    Corresponds to the output of Algorithm 1.
    
    Attributes:
        status: Verification outcome
        k_reached: Final k value achieved (induction depth)
        steps_explored: Total product transitions taken
        counterexample: Path to ERROR if found
        time_elapsed: Verification time in seconds
        message: Human-readable explanation
        
    Usage:
        result = verifier.verify(ts_a, ts_b)
        if result.is_equivalent:
            print("Systems are stutter equivalent!")
        elif result.is_not_equivalent:
            print(f"Counterexample: {result.counterexample}")
    """
    status: VerificationStatus
    k_reached: int
    steps_explored: int
    counterexample: Optional[List[ProductState]] = None
    time_elapsed: float = 0.0
    message: str = ""
    
    @property
    def is_equivalent(self) -> bool:
        """Check if verification proved equivalence."""
        return self.status == VerificationStatus.EQUIVALENT
    
    @property
    def is_not_equivalent(self) -> bool:
        """Check if verification found counterexample."""
        return self.status == VerificationStatus.NOT_EQUIVALENT
    
    @property
    def is_unknown(self) -> bool:
        """Check if verification was inconclusive."""
        return self.status == VerificationStatus.UNKNOWN
    
    @property
    def is_timeout(self) -> bool:
        """Check if verification timed out."""
        return self.status == VerificationStatus.TIMEOUT
    
    @property
    def succeeded(self) -> bool:
        """Check if verification completed successfully (equivalent or not)."""
        return self.status in (VerificationStatus.EQUIVALENT, 
                               VerificationStatus.NOT_EQUIVALENT)
    
    def __repr__(self) -> str:
        return (
            f"VerificationResult(status={self.status.name}, "
            f"k={self.k_reached}, steps={self.steps_explored}, "
            f"time={self.time_elapsed:.3f}s)"
        )
    
    def __str__(self) -> str:
        lines = [
            f"Verification Result: {self.status.name}",
            f"  K-depth reached: {self.k_reached}",
            f"  Steps explored: {self.steps_explored}",
            f"  Time elapsed: {self.time_elapsed:.3f}s",
        ]
        if self.message:
            lines.append(f"  Message: {self.message}")
        if self.counterexample:
            lines.append(f"  Counterexample length: {len(self.counterexample)}")
        return "\n".join(lines)


# ============================================================================
# Progress Callback Type
# ============================================================================

# Callback signature: (current_k, steps_explored, message) -> None
ProgressCallback = Callable[[int, int, str], None]


# ============================================================================
# K-Induction Verifier
# ============================================================================

class KInductionVerifier:
    """
    K-induction verifier for stutter equivalence (Algorithm 1).
    
    Verifies that ERROR is unreachable in the product transition system,
    which implies stutter equivalence by Theorem 1.
    
    Algorithm:
    1. Construct product system TS_×
    2. Define safety invariant P(A, B, phase) ≡ (phase ≠ ERROR)
    3. For k = 1 to k_max:
       a. Base case: Check all paths of length ≤k from initial states
       b. If ERROR found: return NOT_EQUIVALENT with counterexample
       c. Inductive step: Check if P(s₀)∧...∧P(s_{k-1}) -> P(s_k)
       d. If inductive step holds: return EQUIVALENT
    4. Return UNKNOWN if k_max reached
    
    For deterministic systems, this reduces to bounded model checking:
    explore all states up to depth k_max.
    
    Preconditions (Assumptions 1-3):
    - Assumption 1: Initial state correspondence (verified at construction)
    - Assumption 2: Finite stutter depth (assumed, with warning)
    - Assumption 3: No terminal states during verification
    
    Usage:
        verifier = KInductionVerifier(k_max=1000)
        result = verifier.verify(ts_a, ts_b)
        
        if result.is_equivalent:
            print("Proved stutter equivalent!")
        elif result.is_not_equivalent:
            print(f"Diverged at step {len(result.counterexample)}")
    
    Thread Safety:
        Not thread-safe. Create separate instances for concurrent use.
    """
    
    def __init__(
        self,
        k_max: int = 100,
        progress_callback: Optional[ProgressCallback] = None,
        timeout: Optional[float] = None,
        max_steps_per_k: int = 10000,
        check_interval: int = 100
    ):
        """
        Initialize verifier.
        
        Args:
            k_max: Maximum induction depth (Algorithm 1 parameter)
            progress_callback: Called with (current_k, steps_explored, message)
            timeout: Maximum verification time in seconds (None = no limit)
            max_steps_per_k: Maximum steps to explore per k value
            check_interval: Steps between timeout/progress checks
        """
        if k_max < 1:
            raise ValueError(f"k_max must be positive, got {k_max}")
        
        self._k_max = k_max
        self._progress_callback = progress_callback
        self._timeout = timeout
        self._max_steps_per_k = max_steps_per_k
        self._check_interval = check_interval
        
        # Statistics
        self._total_steps = 0
        self._start_time: Optional[float] = None
        
        logger.debug(
            f"Created KInductionVerifier with k_max={k_max}, "
            f"timeout={timeout}, max_steps_per_k={max_steps_per_k}"
        )
    
    # ========================================================================
    # Main Verification Interface
    # ========================================================================
    
    def verify(
        self,
        ts_a: TransitionSystem,
        ts_b: TransitionSystem
    ) -> VerificationResult:
        """
        Verify stutter equivalence between two transition systems.
        
        Implements Algorithm 1 from the theoretical framework.
        
        Args:
            ts_a: First transition system
            ts_b: Second transition system
            
        Returns:
            VerificationResult with status, details, and counterexample if found
        """
        self._start_time = time.time()
        self._total_steps = 0
        
        # Construct product system (verifies Assumption 1)
        try:
            product = ProductTransitionSystem(ts_a, ts_b)
        except ValueError as e:
            # Assumption 1 violated
            elapsed = time.time() - self._start_time
            return VerificationResult(
                status=VerificationStatus.ASSUMPTION_VIOLATED,
                k_reached=0,
                steps_explored=0,
                time_elapsed=elapsed,
                message=f"Assumption 1 violation: {e}"
            )
        
        return self.verify_product(product)
    
    def verify_product(self, product: ProductTransitionSystem) -> VerificationResult:
        """
        Verify an already-constructed product system.
        
        Lower-level interface when product is pre-built.
        
        Args:
            product: Product transition system to verify
            
        Returns:
            VerificationResult
        """
        if self._start_time is None:
            self._start_time = time.time()
        
        self._report_progress(0, 0, "Starting verification")
        
        # Run k-induction algorithm
        result = self._k_induction(product)
        
        return result
    
    # ========================================================================
    # K-Induction Algorithm
    # ========================================================================
    
    def _k_induction(self, product: ProductTransitionSystem) -> VerificationResult:
        """
        Execute the k-induction algorithm.
        
        For deterministic systems, this is equivalent to bounded model checking:
        we explore the single execution path up to k_max steps.
        
        The algorithm terminates when:
        1. ERROR is reached -> NOT_EQUIVALENT
        2. Systems terminate without ERROR -> EQUIVALENT
        3. k_max reached -> UNKNOWN
        4. Timeout -> TIMEOUT
        
        Args:
            product: Product transition system
            
        Returns:
            VerificationResult
        """
        k = 0
        
        while k < self._k_max:
            # Check timeout
            if self._is_timeout():
                elapsed = time.time() - self._start_time
                return VerificationResult(
                    status=VerificationStatus.TIMEOUT,
                    k_reached=k,
                    steps_explored=self._total_steps,
                    time_elapsed=elapsed,
                    message=f"Timeout after {elapsed:.1f}s at k={k}"
                )
            
            # Check if we can continue
            if not product.can_step():
                # Systems terminated without ERROR
                elapsed = time.time() - self._start_time
                self._report_progress(k, self._total_steps, "Systems terminated - equivalent")
                return VerificationResult(
                    status=VerificationStatus.EQUIVALENT,
                    k_reached=k,
                    steps_explored=self._total_steps,
                    time_elapsed=elapsed,
                    message=f"Systems terminated after {k} steps without divergence"
                )
            
            # Take one step in the product system
            product.step()
            self._total_steps += 1
            k += 1
            
            # Check for ERROR (base case violation)
            if product.is_error():
                elapsed = time.time() - self._start_time
                counterexample = product.get_counterexample()
                self._report_progress(k, self._total_steps, "ERROR reached - not equivalent")
                return VerificationResult(
                    status=VerificationStatus.NOT_EQUIVALENT,
                    k_reached=k,
                    steps_explored=self._total_steps,
                    counterexample=counterexample,
                    time_elapsed=elapsed,
                    message=f"Divergence detected at step {k}: {product.last_rule}"
                )
            
            # Progress reporting
            if k % self._check_interval == 0:
                self._report_progress(k, self._total_steps, f"Exploring k={k}")
        
        # k_max reached without conclusion
        elapsed = time.time() - self._start_time
        self._report_progress(self._k_max, self._total_steps, "k_max reached - inconclusive")
        return VerificationResult(
            status=VerificationStatus.UNKNOWN,
            k_reached=self._k_max,
            steps_explored=self._total_steps,
            time_elapsed=elapsed,
            message=f"Reached k_max={self._k_max} without conclusion"
        )
    
    # ========================================================================
    # Advanced K-Induction (for non-deterministic systems)
    # ========================================================================
    
    def _check_base_case(
        self,
        product: ProductTransitionSystem,
        k: int
    ) -> Optional[List[ProductState]]:
        """
        Check base case for depth k.
        
        For deterministic systems, this checks if ERROR is reachable
        within k steps from the initial state.
        
        Args:
            product: Product system to check
            k: Current induction depth
            
        Returns:
            Counterexample path if ERROR reached, None otherwise
            
        Note:
            For non-deterministic systems, this would need to explore
            all possible paths of length ≤k. Our implementation assumes
            deterministic systems (single path).
        """
        steps = 0
        while steps < k and product.can_step():
            product.step()
            steps += 1
            self._total_steps += 1
            
            if product.is_error():
                return product.get_counterexample()
            
            if self._is_timeout():
                return None
        
        return None
    
    def _check_inductive_step(
        self,
        product: ProductTransitionSystem,
        k: int
    ) -> bool:
        """
        Check if k-inductive step holds.
        
        For the safety property P(s) ≡ (phase ≠ ERROR), the inductive
        step checks: if we have k consecutive non-ERROR states, does
        the next state also satisfy P?
        
        For deterministic systems with a single execution path, if we've
        explored k steps without ERROR and the system is still running,
        we need to continue exploring. The inductive step is implicitly
        checked as we explore.
        
        For bounded/finite state systems, termination without ERROR
        implies the inductive step holds vacuously.
        
        Args:
            product: Product system
            k: Induction depth
            
        Returns:
            True if inductive step holds (system terminated or
            k consecutive non-ERROR states don't lead to ERROR)
            
        Note:
            Full k-induction for non-deterministic systems would require
            symbolic execution or SAT/SMT solving to check all paths.
        """
        # For deterministic systems, we check by continuing execution
        # If system has terminated, inductive step holds vacuously
        if not product.can_step():
            return True
        
        # Take one more step and check
        product.step()
        self._total_steps += 1
        
        # If this step leads to ERROR, inductive step fails
        return not product.is_error()
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    def _is_timeout(self) -> bool:
        """Check if timeout has been exceeded."""
        if self._timeout is None:
            return False
        if self._start_time is None:
            return False
        return (time.time() - self._start_time) >= self._timeout
    
    def _report_progress(self, k: int, steps: int, message: str) -> None:
        """Report progress via callback if configured."""
        if self._progress_callback is not None:
            try:
                self._progress_callback(k, steps, message)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")
        
        logger.debug(f"Verification progress: k={k}, steps={steps}, {message}")
    
    @property
    def k_max(self) -> int:
        """Maximum induction depth."""
        return self._k_max
    
    @property
    def timeout(self) -> Optional[float]:
        """Timeout in seconds (None = no limit)."""
        return self._timeout
    
    def __repr__(self) -> str:
        return f"KInductionVerifier(k_max={self._k_max}, timeout={self._timeout})"


# ============================================================================
# Convenience Functions
# ============================================================================

def verify_stutter_equivalence(
    ts_a: TransitionSystem,
    ts_b: TransitionSystem,
    k_max: int = 1000,
    timeout: Optional[float] = None,
    progress_callback: Optional[ProgressCallback] = None
) -> VerificationResult:
    """
    One-shot stutter equivalence verification.
    
    Convenience function that creates a verifier and runs verification.
    
    Args:
        ts_a: First transition system
        ts_b: Second transition system
        k_max: Maximum induction depth
        timeout: Maximum time in seconds
        progress_callback: Progress reporting callback
        
    Returns:
        VerificationResult
        
    Example:
        result = verify_stutter_equivalence(ts_eg, ts_acd, k_max=10000)
        if result.is_equivalent:
            print("Event Graph ≈ Activity Cycle Diagram")
    """
    verifier = KInductionVerifier(
        k_max=k_max,
        timeout=timeout,
        progress_callback=progress_callback
    )
    return verifier.verify(ts_a, ts_b)


def quick_verify(
    ts_a: TransitionSystem,
    ts_b: TransitionSystem,
    max_steps: int = 100
) -> Tuple[bool, Optional[str]]:
    """
    Quick verification with simple boolean result.
    
    For rapid testing and simple use cases.
    
    Args:
        ts_a: First transition system
        ts_b: Second transition system
        max_steps: Maximum steps to check
        
    Returns:
        Tuple of (is_equivalent, error_message)
        - (True, None) if equivalent
        - (False, message) if not equivalent or inconclusive
        
    Example:
        is_equiv, error = quick_verify(ts_a, ts_b)
        assert is_equiv, error
    """
    result = verify_stutter_equivalence(ts_a, ts_b, k_max=max_steps)
    
    if result.is_equivalent:
        return (True, None)
    elif result.is_not_equivalent:
        return (False, f"Diverged at step {result.k_reached}")
    else:
        return (False, f"Inconclusive: {result.message}")


# ============================================================================
# Verification Report Generation
# ============================================================================

def format_verification_report(result: VerificationResult) -> str:
    """
    Generate a detailed verification report.
    
    Args:
        result: Verification result to format
        
    Returns:
        Formatted multi-line report string
    """
    lines = [
        "=" * 60,
        "STUTTER EQUIVALENCE VERIFICATION REPORT",
        "=" * 60,
        "",
        f"Status: {result.status.name}",
        f"K-depth reached: {result.k_reached}",
        f"Steps explored: {result.steps_explored}",
        f"Time elapsed: {result.time_elapsed:.3f} seconds",
        "",
    ]
    
    if result.message:
        lines.append(f"Message: {result.message}")
        lines.append("")
    
    if result.is_equivalent:
        lines.extend([
            "CONCLUSION: Systems are STUTTER EQUIVALENT",
            "",
            "The product transition system reached termination",
            "without entering the ERROR state, proving that",
            "the two systems produce stutter-equivalent traces.",
        ])
    elif result.is_not_equivalent:
        lines.extend([
            "CONCLUSION: Systems are NOT STUTTER EQUIVALENT",
            "",
            "A counterexample was found demonstrating divergence.",
        ])
        if result.counterexample:
            lines.extend([
                "",
                f"Counterexample (length {len(result.counterexample)}):",
            ])
            for i, state in enumerate(result.counterexample[:10]):  # Show first 10
                lines.append(f"  Step {i}: {state}")
            if len(result.counterexample) > 10:
                lines.append(f"  ... ({len(result.counterexample) - 10} more steps)")
    elif result.is_timeout:
        lines.extend([
            "CONCLUSION: TIMEOUT",
            "",
            "Verification timed out before reaching a conclusion.",
            "Try increasing the timeout or reducing model complexity.",
        ])
    else:
        lines.extend([
            "CONCLUSION: UNKNOWN",
            "",
            "Verification reached maximum depth without conclusion.",
            "Try increasing k_max or check if the model is correct.",
        ])
    
    lines.extend(["", "=" * 60])
    return "\n".join(lines)


def format_counterexample(counterexample: List[ProductState]) -> str:
    """
    Format a counterexample for display.
    
    Args:
        counterexample: List of product states leading to ERROR
        
    Returns:
        Formatted string showing the path to divergence
    """
    if not counterexample:
        return "No counterexample available"
    
    lines = [
        "Counterexample Path:",
        "-" * 40,
    ]
    
    for i, state in enumerate(counterexample):
        phase_str = str(state.phase)
        lines.append(
            f"Step {state.step_number}: "
            f"A={_format_label_set(state.label_a)}, "
            f"B={_format_label_set(state.label_b)}, "
            f"phase={phase_str}"
        )
    
    lines.append("-" * 40)
    return "\n".join(lines)


def _format_label_set(label_set) -> str:
    """Format a label set for display."""
    if not label_set:
        return "{}"
    names = sorted(label.name for label in label_set)
    return "{" + ", ".join(names) + "}"