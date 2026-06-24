"""
verification/msre.py

Macro-step refinement equivalence (MSRE) verification.

Implements the 2-phase (BSync/Error) product TS from Chapter 9 Section 9.5.3.
Each product transition advances both systems to their next tick boundary,
then checks observable coupling: L(B_k^{F_1}) = L(B_k^{F_2}).

Tick boundaries are detected by simulation clock advance, not explicit
quiescence checking. This requires no formalism-specific logic.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from simasm.log.logger import get_logger
from .ts import TransitionSystem
from .label import LabelSet, format_label_set

logger = get_logger(__name__)


@dataclass
class MSREBoundary:
    """State snapshot at a tick boundary."""
    k: int
    sim_time: float
    label: LabelSet
    steps_in_tick: int


@dataclass
class MSREFailure:
    """Counterexample information when MSRE fails."""
    boundary_k: int
    reason: str
    sim_time_a: float
    sim_time_b: float
    label_a: LabelSet
    label_b: LabelSet


@dataclass
class MSREResult:
    """Result of MSRE verification for a single seed."""
    seed: int
    is_equivalent: bool
    boundaries_checked: int
    total_steps_a: int
    total_steps_b: int
    step_profile: List[Tuple[int, int]] = field(default_factory=list)
    failure: Optional[MSREFailure] = None

    @property
    def step_profile_summary(self) -> dict:
        if not self.step_profile:
            return {}
        m_vals = [p[0] for p in self.step_profile]
        n_vals = [p[1] for p in self.step_profile]
        return {
            "m_mean": sum(m_vals) / len(m_vals),
            "m_range": [min(m_vals), max(m_vals)],
            "n_mean": sum(n_vals) / len(n_vals),
            "n_range": [min(n_vals), max(n_vals)],
        }


class MacroStepRefinementVerifier:
    """
    Macro-step refinement equivalence verifier (Chapter 9).

    Advances both systems independently to tick boundaries, then checks
    observable coupling via label equality.
    """

    def __init__(self, ts_a: TransitionSystem, ts_b: TransitionSystem):
        self._ts_a = ts_a
        self._ts_b = ts_b

    def verify(self, seed: int = 0,
               max_boundaries: Optional[int] = None) -> MSREResult:
        """Run MSRE verification to completion or max_boundaries."""
        label_a = self._ts_a.current_label
        label_b = self._ts_b.current_label

        if label_a != label_b:
            return MSREResult(
                seed=seed,
                is_equivalent=False,
                boundaries_checked=0,
                total_steps_a=0,
                total_steps_b=0,
                failure=MSREFailure(
                    boundary_k=0,
                    reason="initial_mismatch",
                    sim_time_a=self._ts_a.sim_time,
                    sim_time_b=self._ts_b.sim_time,
                    label_a=label_a,
                    label_b=label_b,
                ),
            )

        prev_time_a = self._ts_a.sim_time
        prev_time_b = self._ts_b.sim_time
        prev_obs_a = label_a
        prev_obs_b = label_b
        k = 0
        total_steps_a = 0
        total_steps_b = 0
        step_profile: List[Tuple[int, int]] = []

        while self._ts_a.can_step() or self._ts_b.can_step():
            # Advance A to next tick boundary
            steps_a = 0
            while self._ts_a.can_step():
                self._ts_a.step()
                steps_a += 1
                if self._ts_a.sim_time > prev_time_a:
                    break
                prev_obs_a = self._ts_a.current_label

            boundary_time_a = prev_time_a
            prev_time_a = self._ts_a.sim_time

            # Advance B to next tick boundary
            steps_b = 0
            while self._ts_b.can_step():
                self._ts_b.step()
                steps_b += 1
                if self._ts_b.sim_time > prev_time_b:
                    break
                prev_obs_b = self._ts_b.current_label

            boundary_time_b = prev_time_b
            prev_time_b = self._ts_b.sim_time

            k += 1
            total_steps_a += steps_a
            total_steps_b += steps_b
            step_profile.append((steps_a, steps_b))

            def _fail(reason):
                return MSREResult(
                    seed=seed,
                    is_equivalent=False,
                    boundaries_checked=k,
                    total_steps_a=total_steps_a,
                    total_steps_b=total_steps_b,
                    step_profile=step_profile,
                    failure=MSREFailure(
                        boundary_k=k,
                        reason=reason,
                        sim_time_a=boundary_time_a,
                        sim_time_b=boundary_time_b,
                        label_a=prev_obs_a,
                        label_b=prev_obs_b,
                    ),
                )

            terminated_a = not self._ts_a.can_step()
            terminated_b = not self._ts_b.can_step()
            if terminated_a != terminated_b:
                return _fail("termination_mismatch")

            if abs(boundary_time_a - boundary_time_b) > 1e-10:
                return _fail("time_divergence")

            if prev_obs_a != prev_obs_b:
                return _fail("label_mismatch")

            prev_obs_a = self._ts_a.current_label
            prev_obs_b = self._ts_b.current_label

            if max_boundaries is not None and k >= max_boundaries:
                break

        return MSREResult(
            seed=seed,
            is_equivalent=True,
            boundaries_checked=k,
            total_steps_a=total_steps_a,
            total_steps_b=total_steps_b,
            step_profile=step_profile,
        )


def verify_msre(
    ts_a: TransitionSystem,
    ts_b: TransitionSystem,
    seed: int = 0,
    max_boundaries: Optional[int] = None,
) -> MSREResult:
    """One-shot MSRE verification."""
    verifier = MacroStepRefinementVerifier(ts_a, ts_b)
    return verifier.verify(seed=seed, max_boundaries=max_boundaries)
