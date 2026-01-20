"""
simulation/collector.py

Statistics collector that hooks into simulation stepper.

Provides:
- ExpressionParser: Parses expression strings into AST
- StatisticsCollector: Collects statistics during simulation

Usage:
    from simasm.simulation.collector import StatisticsCollector
    
    collector = StatisticsCollector(
        configs=[
            StatisticConfig(name="avg_queue", type="time_average", expr="lib.length(queue)"),
            StatisticConfig(name="util", type="utilization", expr="server_busy"),
        ],
        state=state,
        term_evaluator=evaluator
    )
    
    # During simulation loop
    collector.on_step(state, sim_time)
    
    # After simulation
    collector.finalize(end_time=1000.0, warmup_time=100.0)
    results = collector.get_results()
"""

from typing import Dict, List, Any, Optional, Set, TYPE_CHECKING
from pathlib import Path

from lark import Lark, LarkError

from simasm.log.logger import get_logger
from simasm.core.state import ASMState, ASMObject
from simasm.parser.transformer import SimASMTransformer

from .config import StatisticConfig, StatisticType
from .statistics import (
    Statistic,
    StatisticResult,
    CountStatistic,
    TimeAverageStatistic,
    UtilizationStatistic,
    DurationStatistic,
    TimeSeriesStatistic,
    ObservationStatistic,
    create_statistic,
)

if TYPE_CHECKING:
    from simasm.core.terms import TermEvaluator, Environment

logger = get_logger(__name__)


# ============================================================================
# Expression Parser
# ============================================================================

class ExpressionParser:
    """
    Parses expression strings into AST nodes.
    
    Uses the SimASM grammar but with 'expr' as the start rule.
    
    Usage:
        parser = ExpressionParser()
        ast = parser.parse("lib.length(queue) + 1")
    """
    
    GRAMMAR_FILE = Path(__file__).parent.parent / "parser" / "grammar.lark"
    
    def __init__(self):
        """Create expression parser."""
        self._grammar = self._load_grammar()
        self._transformer = SimASMTransformer()
        self._parser = Lark(
            self._grammar,
            start="expr",
            parser="lalr",
            transformer=self._transformer
        )
    
    def _load_grammar(self) -> str:
        """Load grammar from file."""
        if not self.GRAMMAR_FILE.exists():
            raise RuntimeError(f"Grammar file not found: {self.GRAMMAR_FILE}")
        return self.GRAMMAR_FILE.read_text()
    
    def parse(self, expr_string: str) -> Any:
        """
        Parse expression string to AST.
        
        Args:
            expr_string: Expression string (e.g., "x + 1", "lib.length(q)")
        
        Returns:
            AST node representing the expression
        
        Raises:
            ValueError: If parsing fails
        """
        try:
            return self._parser.parse(expr_string)
        except LarkError as e:
            raise ValueError(f"Failed to parse expression '{expr_string}': {e}") from e


# Singleton expression parser
_expr_parser: Optional[ExpressionParser] = None


def get_expression_parser() -> ExpressionParser:
    """Get or create singleton expression parser."""
    global _expr_parser
    if _expr_parser is None:
        _expr_parser = ExpressionParser()
    return _expr_parser


def parse_expression(expr_string: str) -> Any:
    """
    Parse expression string to AST.
    
    Convenience function using shared parser instance.
    
    Args:
        expr_string: Expression string
    
    Returns:
        AST node
    """
    return get_expression_parser().parse(expr_string)


# ============================================================================
# Statistics Collector
# ============================================================================

class StatisticsCollector:
    """
    Collects statistics during a simulation run.
    
    Hooks into stepper to receive state updates and evaluates
    expressions against the current state to update statistics.
    
    Usage:
        collector = StatisticsCollector(
            configs=experiment_config.statistics,
            state=state,
            term_evaluator=evaluator
        )
        
        # Simulation loop
        while sim_time < end_time:
            stepper.step()
            collector.on_step(state, sim_time)
        
        # Finalize and get results
        collector.finalize(end_time, warmup_time)
        results = collector.get_results()
    """
    
    def __init__(
        self,
        configs: List[StatisticConfig],
        state: Optional[ASMState] = None,
        term_evaluator: Optional['TermEvaluator'] = None,
        environment: Optional['Environment'] = None
    ):
        """
        Create statistics collector.
        
        Args:
            configs: List of statistic configurations
            state: ASM state (optional, can be set later)
            term_evaluator: Term evaluator for expression evaluation
            environment: Environment for variable lookups
        """
        self._configs = configs
        self._state = state
        self._evaluator = term_evaluator
        self._environment = environment
        
        # Statistics indexed by name
        self._statistics: Dict[str, Statistic] = {}

        # Parsed expression ASTs for each statistic
        self._expr_asts: Dict[str, Any] = {}
        self._condition_asts: Dict[str, Any] = {}

        # For lifecycle duration tracking
        self._start_expr_asts: Dict[str, Any] = {}
        self._end_expr_asts: Dict[str, Any] = {}

        # Domain tracking for count statistics
        self._count_domains: Dict[str, str] = {}  # stat_name -> domain_name
        self._tracked_objects: Dict[str, Set[int]] = {}  # stat_name -> set of object ids

        # Trace collection for plotting
        self._trace_configs: Dict[str, StatisticConfig] = {}  # stats with trace=True
        self._trace_buffers: Dict[str, List[tuple]] = {}  # stat_name -> [(time, value), ...]
        self._last_trace_time: Dict[str, float] = {}  # stat_name -> last sample time
        self._warmup_time: float = 0.0  # Will be set via set_trace_config()
        self._trace_interval: float = 1.0  # Default trace interval

        # Build statistics from configs
        self._build_statistics()
    
    def _build_statistics(self) -> None:
        """Build Statistic instances from configs and parse expressions."""
        expr_parser = get_expression_parser()
        
        for config in self._configs:
            # Create statistic instance
            stat = create_statistic(config)
            self._statistics[config.name] = stat
            
            # Parse main expression
            if config.expr:
                try:
                    self._expr_asts[config.name] = expr_parser.parse(config.expr)
                except ValueError as e:
                    logger.error(f"Failed to parse expr for '{config.name}': {e}")
                    raise
            
            # Parse condition expression
            if config.condition:
                try:
                    self._condition_asts[config.name] = expr_parser.parse(config.condition)
                except ValueError as e:
                    logger.error(f"Failed to parse condition for '{config.name}': {e}")
                    raise
            
            # Parse lifecycle expressions for duration
            if config.start_expr:
                try:
                    self._start_expr_asts[config.name] = expr_parser.parse(config.start_expr)
                except ValueError as e:
                    logger.error(f"Failed to parse start_expr for '{config.name}': {e}")
                    raise
            
            if config.end_expr:
                try:
                    self._end_expr_asts[config.name] = expr_parser.parse(config.end_expr)
                except ValueError as e:
                    logger.error(f"Failed to parse end_expr for '{config.name}': {e}")
                    raise
            
            # Track domains for count statistics
            if config.type == StatisticType.COUNT.value and config.domain:
                self._count_domains[config.name] = config.domain
                self._tracked_objects[config.name] = set()

            # Initialize trace buffer if trace=True
            if config.trace:
                self._trace_configs[config.name] = config
                self._trace_buffers[config.name] = []
                self._last_trace_time[config.name] = -float('inf')

        logger.info(f"Built {len(self._statistics)} statistics ({len(self._trace_configs)} with tracing)")
    
    def set_state(self, state: ASMState) -> None:
        """Set the ASM state to collect from."""
        self._state = state
    
    def set_evaluator(self, evaluator: 'TermEvaluator') -> None:
        """Set the term evaluator."""
        self._evaluator = evaluator
    
    def set_environment(self, env: 'Environment') -> None:
        """Set the environment for variable lookups."""
        self._environment = env

    def set_trace_config(self, warmup_time: float, trace_interval: float) -> None:
        """
        Set trace collection configuration.

        Args:
            warmup_time: Warmup period before starting trace collection
            trace_interval: Time interval between trace samples
        """
        self._warmup_time = warmup_time
        self._trace_interval = trace_interval
    
    def _evaluate_expr(self, name: str, sim_time: float) -> Any:
        """
        Evaluate expression for a statistic.
        
        Args:
            name: Statistic name
            sim_time: Current simulation time
        
        Returns:
            Evaluated value or None if evaluation fails
        """
        if name not in self._expr_asts:
            return None
        
        if self._evaluator is None:
            logger.warning(f"No evaluator set, cannot evaluate expression for '{name}'")
            return None
        
        ast = self._expr_asts[name]
        env = self._environment
        
        try:
            return self._evaluator.eval(ast, env)
        except Exception as e:
            logger.debug(f"Error evaluating expression for '{name}': {e}")
            return None
    
    def _evaluate_condition(self, name: str, sim_time: float) -> bool:
        """
        Evaluate condition for a statistic.
        
        Args:
            name: Statistic name
            sim_time: Current simulation time
        
        Returns:
            True if condition passes (or no condition), False otherwise
        """
        if name not in self._condition_asts:
            return True  # No condition means always collect
        
        if self._evaluator is None:
            return True
        
        ast = self._condition_asts[name]
        env = self._environment
        
        try:
            result = self._evaluator.eval(ast, env)
            return bool(result)
        except Exception as e:
            logger.debug(f"Error evaluating condition for '{name}': {e}")
            return False
    
    def on_step(self, state: ASMState, sim_time: float) -> None:
        """
        Called after each simulation step.
        
        Evaluates expressions and updates all statistics.
        
        Args:
            state: Current ASM state
            sim_time: Current simulation time
        """
        self._state = state
        
        for name, stat in self._statistics.items():
            config = stat.config
            
            # Check condition
            if not self._evaluate_condition(name, sim_time):
                continue
            
            # Handle different statistic types
            stat_type = config.statistic_type
            
            if stat_type == StatisticType.COUNT:
                # Count can work two ways:
                # 1. With domain: track new objects created in that domain
                # 2. With expr: read a counter value from the model
                if name in self._expr_asts:
                    # Expression-based count: read counter value directly
                    value = self._evaluate_expr(name, sim_time)
                    if value is not None:
                        # Store as final value (will be overwritten each step)
                        stat._final_value = value
                elif name in self._count_domains:
                    # Domain-based count: track new objects
                    self._update_count_from_state(name, state, sim_time)
            
            elif stat_type == StatisticType.TIME_AVERAGE:
                value = self._evaluate_expr(name, sim_time)
                if value is not None:
                    stat.update(value, sim_time)
            
            elif stat_type == StatisticType.UTILIZATION:
                value = self._evaluate_expr(name, sim_time)
                if value is not None:
                    stat.update(bool(value), sim_time)
            
            elif stat_type == StatisticType.DURATION:
                if config.is_lifecycle_duration:
                    # Lifecycle tracking handled separately
                    pass
                else:
                    value = self._evaluate_expr(name, sim_time)
                    if value is not None:
                        stat.update(value, sim_time)
            
            elif stat_type == StatisticType.TIME_SERIES:
                value = self._evaluate_expr(name, sim_time)
                if value is not None:
                    stat.update(value, sim_time)
            
            elif stat_type == StatisticType.OBSERVATION:
                value = self._evaluate_expr(name, sim_time)
                if value is not None:
                    stat.update(value, sim_time)

        # Capture trace samples for statistics with trace=True
        self._capture_traces(sim_time)

    def _capture_traces(self, sim_time: float) -> None:
        """
        Capture trace samples for statistics with trace=True.

        Samples are captured at fixed intervals (self._trace_interval)
        and only after the warmup period.

        Args:
            sim_time: Current simulation time
        """
        # Skip if before warmup
        if sim_time < self._warmup_time:
            return

        for name, config in self._trace_configs.items():
            # Check if it's time to sample
            last_time = self._last_trace_time[name]
            if sim_time - last_time >= self._trace_interval:
                # Evaluate expression for this statistic
                value = self._evaluate_expr(name, sim_time)
                if value is not None:
                    # Store (time, value) pair
                    self._trace_buffers[name].append((sim_time, value))
                    self._last_trace_time[name] = sim_time

    def _update_count_from_state(
        self, 
        name: str, 
        state: ASMState, 
        sim_time: float
    ) -> None:
        """
        Update count statistic by checking domain objects.
        
        Counts new objects that weren't seen before.
        
        Args:
            name: Statistic name
            state: Current ASM state
            sim_time: Current simulation time
        """
        if name not in self._count_domains:
            return
        
        domain_name = self._count_domains[name]
        stat = self._statistics[name]
        tracked = self._tracked_objects[name]
        
        # Get all objects in the domain
        try:
            domain_objects = state.get_domain_objects(domain_name)
            
            # Count new objects
            for obj in domain_objects:
                obj_id = id(obj)
                if obj_id not in tracked:
                    tracked.add(obj_id)
                    stat.update(1, sim_time)
        except Exception as e:
            logger.debug(f"Error counting domain '{domain_name}': {e}")
    
    def on_object_created(
        self, 
        obj: ASMObject, 
        domain: str, 
        sim_time: float
    ) -> None:
        """
        Called when a new object is created.
        
        Updates count statistics for the object's domain.
        
        Args:
            obj: The created object
            domain: Domain name
            sim_time: Creation time
        """
        # Update any count statistics tracking this domain
        for name, tracked_domain in self._count_domains.items():
            if tracked_domain == domain:
                stat = self._statistics[name]
                
                # Check condition
                if self._evaluate_condition(name, sim_time):
                    # Track object to avoid double counting
                    obj_id = id(obj)
                    if obj_id not in self._tracked_objects[name]:
                        self._tracked_objects[name].add(obj_id)
                        stat.update(1, sim_time)
    
    def on_entity_start(
        self, 
        stat_name: str, 
        entity_id: Any, 
        sim_time: float
    ) -> None:
        """
        Called when an entity starts for lifecycle duration tracking.
        
        Args:
            stat_name: Name of duration statistic
            entity_id: Unique entity identifier
            sim_time: Start time
        """
        if stat_name in self._statistics:
            stat = self._statistics[stat_name]
            if isinstance(stat, DurationStatistic):
                stat.start_entity(entity_id, sim_time)
    
    def on_entity_end(
        self, 
        stat_name: str, 
        entity_id: Any, 
        sim_time: float
    ) -> None:
        """
        Called when an entity ends for lifecycle duration tracking.
        
        Args:
            stat_name: Name of duration statistic
            entity_id: Unique entity identifier
            sim_time: End time
        """
        if stat_name in self._statistics:
            stat = self._statistics[stat_name]
            if isinstance(stat, DurationStatistic):
                stat.end_entity(entity_id, sim_time)
    
    def finalize(self, end_time: float, warmup_time: float = 0.0) -> None:
        """
        Finalize all statistics after simulation run.
        
        Args:
            end_time: Simulation end time
            warmup_time: Warmup period to exclude
        """
        for stat in self._statistics.values():
            stat.finalize(end_time, warmup_time)
        
        logger.info(f"Finalized {len(self._statistics)} statistics")
    
    def get_results(self) -> Dict[str, StatisticResult]:
        """
        Get all statistic results.

        Returns:
            Dictionary mapping statistic name to StatisticResult
        """
        results = {}
        for name, stat in self._statistics.items():
            result = stat.get_result()
            # Attach trace data if available
            if name in self._trace_buffers and self._trace_buffers[name]:
                result.raw_values = self._trace_buffers[name]
            results[name] = result
        return results
    
    def get_values(self) -> Dict[str, Any]:
        """
        Get primary values for all statistics.
        
        Returns:
            Dictionary mapping statistic name to primary value
        """
        return {
            name: stat.get_value()
            for name, stat in self._statistics.items()
        }
    
    def get_statistic(self, name: str) -> Optional[Statistic]:
        """
        Get a specific statistic by name.
        
        Args:
            name: Statistic name
        
        Returns:
            Statistic instance or None if not found
        """
        return self._statistics.get(name)
    
    def reset(self) -> None:
        """Reset all statistics for a new replication."""
        for stat in self._statistics.values():
            stat.reset()
        
        # Reset tracked objects for count statistics
        for name in self._tracked_objects:
            self._tracked_objects[name] = set()
        
        logger.debug("Reset all statistics")
    
    @property
    def statistic_names(self) -> List[str]:
        """Get list of all statistic names."""
        return list(self._statistics.keys())
    
    @property
    def statistic_count(self) -> int:
        """Get number of statistics."""
        return len(self._statistics)
