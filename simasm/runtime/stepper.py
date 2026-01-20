"""
runtime/stepper.py

Step-by-step ASM execution engine.

Provides:
- Stepper: Abstract base class for step execution
- ASMStepper: Concrete implementation for ASM models

Key concepts:
- Each step() call executes the main rule once
- Simulation time is tracked via a state variable
- Stop conditions control when simulation ends
- Supports both step-based and time-based execution

Usage:
    stepper = ASMStepper(state, main_rule, evaluator)
    
    # Step-by-step
    while stepper.can_step():
        stepper.step()
    
    # Or run to completion
    stepper.run(max_steps=1000)
    
    # Or run until time
    stepper.run_until(end_time=100.0)
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, List, Any
from dataclasses import dataclass, field

from simasm.core.state import ASMState, UNDEF
from simasm.core.rules import RuleDefinition, RuleEvaluator, RuleRegistry
from simasm.core.terms import Environment
from simasm.log.logger import get_logger

logger = get_logger(__name__)


class StepperError(Exception):
    """Raised when stepper operations fail."""
    pass


class Stepper(ABC):
    """
    Abstract base class for step-by-step execution.
    
    Defines the interface for executing simulation steps.
    Subclasses implement specific execution semantics.
    """
    
    @abstractmethod
    def current_state(self) -> ASMState:
        """Return the current ASM state."""
        pass
    
    @abstractmethod
    def step(self) -> bool:
        """
        Execute one step.
        
        Returns:
            True if step was executed, False if cannot step
        """
        pass
    
    @abstractmethod
    def can_step(self) -> bool:
        """
        Check if another step can be executed.
        
        Returns:
            True if step() would succeed, False otherwise
        """
        pass
    
    @property
    @abstractmethod
    def sim_time(self) -> float:
        """Return current simulation time."""
        pass
    
    @property
    @abstractmethod
    def step_count(self) -> int:
        """Return number of steps executed."""
        pass


@dataclass
class StepperConfig:
    """
    Configuration for ASMStepper.
    
    Attributes:
        time_var: Name of state variable holding simulation time
        max_steps: Maximum steps before stopping (None = unlimited)
        end_time: Maximum simulation time (None = unlimited)
        stop_on_fixpoint: Stop when state doesn't change
        trace_enabled: Record state trace for debugging
    """
    time_var: str = "sim_clocktime"
    max_steps: Optional[int] = None
    end_time: Optional[float] = None
    stop_on_fixpoint: bool = False
    trace_enabled: bool = False


@dataclass
class StepResult:
    """
    Result of a single step execution.
    
    Attributes:
        step_number: Which step this was (1-indexed)
        sim_time: Simulation time after step
        updates_count: Number of state updates
        is_fixpoint: True if no updates were made
    """
    step_number: int
    sim_time: float
    updates_count: int
    is_fixpoint: bool


class ASMStepper(Stepper):
    """
    Concrete stepper for ASM model execution.
    
    Executes the main rule repeatedly, tracking simulation time
    and applying stop conditions.
    
    Usage:
        # Basic setup
        stepper = ASMStepper(state, main_rule, evaluator)
        stepper.run(max_steps=1000)
        
        # With configuration
        config = StepperConfig(time_var="clock", end_time=100.0)
        stepper = ASMStepper(state, main_rule, evaluator, config)
        stepper.run_until(50.0)
        
        # Manual stepping
        while stepper.can_step():
            result = stepper.step()
            print(f"Step {result.step_number}: time={result.sim_time}")
    
    Stop conditions (checked in order):
    1. max_steps reached
    2. end_time exceeded
    3. Custom stop_condition returns True
    4. stop_on_fixpoint and no updates made
    """
    
    def __init__(
        self,
        state: ASMState,
        main_rule: RuleDefinition,
        rule_evaluator: RuleEvaluator,
        config: Optional[StepperConfig] = None,
        stop_condition: Optional[Callable[[ASMState], bool]] = None,
    ):
        """
        Initialize ASMStepper.
        
        Args:
            state: Initial ASM state
            main_rule: The main rule to execute each step
            rule_evaluator: Evaluator for rule execution
            config: Optional configuration (defaults used if None)
            stop_condition: Optional custom stop condition
        """
        self._state = state
        self._main_rule = main_rule
        self._evaluator = rule_evaluator
        self._config = config or StepperConfig()
        self._stop_condition = stop_condition
        
        self._step_count = 0
        self._stopped = False
        self._stop_reason: Optional[str] = None
        self._trace: List[StepResult] = []
        
        # Initialize simulation time if not set
        current_time = self._state.get_var(self._config.time_var)
        if current_time is UNDEF:
            self._state.set_var(self._config.time_var, 0.0)
            logger.debug(f"Initialized {self._config.time_var} to 0.0")
        
        logger.debug(f"Created ASMStepper with main rule '{main_rule.name}'")
    
    @property
    def state(self) -> ASMState:
        """Return the current ASM state."""
        return self._state
    
    def current_state(self) -> ASMState:
        """Return the current ASM state."""
        return self._state
    
    @property
    def sim_time(self) -> float:
        """Return current simulation time."""
        time_val = self._state.get_var(self._config.time_var)
        if time_val is UNDEF:
            return 0.0
        return float(time_val)
    
    @property
    def step_count(self) -> int:
        """Return number of steps executed."""
        return self._step_count
    
    @property
    def stop_reason(self) -> Optional[str]:
        """Return reason for stopping (None if still running)."""
        return self._stop_reason
    
    @property
    def trace(self) -> List[StepResult]:
        """Return execution trace (if trace_enabled)."""
        return self._trace.copy()
    
    def can_step(self) -> bool:
        """
        Check if another step can be executed.
        
        Returns:
            True if no stop condition is met
        """
        if self._stopped:
            return False
        
        # Check max_steps
        if self._config.max_steps is not None:
            if self._step_count >= self._config.max_steps:
                self._stop_reason = f"max_steps ({self._config.max_steps}) reached"
                self._stopped = True
                return False
        
        # Check end_time
        if self._config.end_time is not None:
            if self.sim_time >= self._config.end_time:
                self._stop_reason = f"end_time ({self._config.end_time}) reached"
                self._stopped = True
                return False
        
        # Check custom stop condition
        if self._stop_condition is not None:
            if self._stop_condition(self._state):
                self._stop_reason = "custom stop_condition"
                self._stopped = True
                return False
        
        return True
    
    def step(self) -> StepResult:
        """
        Execute one step of the main rule.
        
        Returns:
            StepResult with step information
            
        Raises:
            StepperError: If cannot step
        """
        if not self.can_step():
            raise StepperError(f"Cannot step: {self._stop_reason or 'stopped'}")
        
        self._step_count += 1
        
        # Execute main rule
        env = Environment()
        updates = self._evaluator.eval(self._main_rule.body, env)
        
        # Apply updates to state
        updates.apply_to(self._state)
        
        # Check for fixpoint
        is_fixpoint = len(updates) == 0
        if is_fixpoint and self._config.stop_on_fixpoint:
            self._stop_reason = "fixpoint (no updates)"
            self._stopped = True
        
        # Create result
        result = StepResult(
            step_number=self._step_count,
            sim_time=self.sim_time,
            updates_count=len(updates),
            is_fixpoint=is_fixpoint,
        )
        
        # Record trace if enabled
        if self._config.trace_enabled:
            self._trace.append(result)
        
        logger.debug(
            f"Step {result.step_number}: time={result.sim_time:.4f}, "
            f"updates={result.updates_count}, fixpoint={result.is_fixpoint}"
        )
        
        return result
    
    def run(self, max_steps: Optional[int] = None) -> ASMState:
        """
        Run until stop condition or max_steps.
        
        Args:
            max_steps: Override config.max_steps for this run
        
        Returns:
            Final ASM state
        """
        # Temporarily override max_steps if provided
        original_max = self._config.max_steps
        if max_steps is not None:
            self._config.max_steps = self._step_count + max_steps
        
        try:
            while self.can_step():
                self.step()
        finally:
            # Restore original
            self._config.max_steps = original_max
        
        logger.info(
            f"Run completed: {self._step_count} steps, "
            f"time={self.sim_time:.4f}, reason={self._stop_reason}"
        )
        
        return self._state
    
    def run_until(self, end_time: float) -> ASMState:
        """
        Run until simulation time reaches end_time.
        
        Args:
            end_time: Target simulation time
        
        Returns:
            Final ASM state
        """
        # Temporarily set end_time
        original_end = self._config.end_time
        self._config.end_time = end_time
        
        # Reset stopped flag if we're extending
        if self._stopped and self._stop_reason and "end_time" in self._stop_reason:
            self._stopped = False
            self._stop_reason = None
        
        try:
            while self.can_step():
                self.step()
        finally:
            # Restore original
            self._config.end_time = original_end
        
        logger.info(
            f"Run until {end_time} completed: {self._step_count} steps, "
            f"time={self.sim_time:.4f}"
        )
        
        return self._state
    
    def reset(self, state: Optional[ASMState] = None) -> None:
        """
        Reset stepper for a new run.
        
        Args:
            state: Optional new state (keeps current if None)
        """
        if state is not None:
            self._state = state
        
        self._step_count = 0
        self._stopped = False
        self._stop_reason = None
        self._trace.clear()
        
        logger.debug("Stepper reset")


@dataclass
class DESStepperConfig(StepperConfig):
    """
    Configuration specific to Discrete Event Simulation.
    
    Extends StepperConfig with DES-specific options.
    
    Attributes:
        fel_var: Name of Future Event List variable
        empty_fel_stops: Stop when FEL is empty
    """
    fel_var: str = "future_event_list"
    empty_fel_stops: bool = True


class DESStepper(ASMStepper):
    """
    Stepper specialized for Discrete Event Simulation.
    
    Adds DES-specific features:
    - Stops when FEL is empty (configurable)
    - Tracks events processed
    - Supports warm-up period
    
    Usage:
        config = DESStepperConfig(
            time_var="sim_clocktime",
            fel_var="FEL",
            end_time=1000.0,
        )
        stepper = DESStepper(state, main_rule, evaluator, config)
        stepper.run()
    """
    
    def __init__(
        self,
        state: ASMState,
        main_rule: RuleDefinition,
        rule_evaluator: RuleEvaluator,
        config: Optional[DESStepperConfig] = None,
        stop_condition: Optional[Callable[[ASMState], bool]] = None,
    ):
        """Initialize DESStepper."""
        config = config or DESStepperConfig()
        super().__init__(state, main_rule, rule_evaluator, config, stop_condition)
        self._des_config = config
        self._events_processed = 0
    
    @property
    def events_processed(self) -> int:
        """Return number of events processed."""
        return self._events_processed
    
    def can_step(self) -> bool:
        """Check if can step, including FEL check."""
        if not super().can_step():
            return False
        
        # Check if FEL is empty
        if self._des_config.empty_fel_stops:
            fel = self._state.get_var(self._des_config.fel_var)
            if fel is UNDEF or (isinstance(fel, list) and len(fel) == 0):
                self._stop_reason = "FEL empty"
                self._stopped = True
                return False
        
        return True
    
    def step(self) -> StepResult:
        """Execute one DES step (process one event)."""
        result = super().step()
        self._events_processed += 1
        return result
    
    def reset(self, state: Optional[ASMState] = None) -> None:
        """Reset DESStepper."""
        super().reset(state)
        self._events_processed = 0
