"""
Event Graph Framework Module for O2DESpy

Provides EventGraphModel — a Sandbox subclass that reads Event Graph JSON
specifications and executes them using O2DESpy's event-scheduling kernel.

The EG algorithm (next-event time-advance):
  1. Event fires -> execute state_change assignments
  2. For each outgoing scheduling edge: evaluate condition, if true schedule target
  3. Sandbox advances clock to next event

No code generation needed — the JSON spec is interpreted at runtime.

Usage:
    from o2despy_eg.event_graph_model import EventGraphModel

    model = EventGraphModel.from_json("tandem_2_eg.json", seed=42)
    model.run(duration=timedelta(hours=10000))
    print(model.departure_count)
"""

import json
import random
import re
from datetime import timedelta
from pathlib import Path

from .sandbox import Sandbox


class EventGraphModel(Sandbox):
    """O2DESpy Sandbox subclass that executes an Event Graph specification.

    Reads an EG JSON spec (vertices, scheduling edges, state variables,
    random streams, parameters) and creates a runnable simulation model.
    """

    def __init__(self, spec: dict, seed: int = 0):
        """Initialize from an EG specification dict.

        Args:
            spec: Parsed EG JSON specification.
            seed: Random seed for reproducibility.
        """
        model_name = spec.get("model_name", "EventGraphModel")
        super().__init__(seed=seed, code=model_name)

        self._spec = spec
        self._vertex_map = {}       # name -> vertex dict
        self._edges_from = {}       # vertex_name -> list of edges
        self._random_streams = {}   # stream_name -> (distribution, params)

        # Parse parameters
        self._params = {}
        for pname, pdef in spec.get("parameters", {}).items():
            self._params[pname] = pdef["value"]

        # Initialize state variables as instance attributes
        self._state_var_names = []
        for sv_name, sv_def in spec.get("state_variables", {}).items():
            initial = sv_def.get("initial", 0)
            setattr(self, sv_name, initial)
            self._state_var_names.append(sv_name)

        # Ensure departure_count and in_system exist
        if not hasattr(self, "departure_count"):
            self.departure_count = 0

        # Track in_system from observables if defined
        self._in_system_expr = None
        for obs_name, obs_def in spec.get("observables", {}).items():
            if obs_name == "in_system":
                self._in_system_expr = obs_def.get("expression", "")
        self.in_system = 0

        # Area accumulators
        self._last_event_time = None
        self._area_queue_total = 0.0
        self._area_system = 0.0

        # Build queue expression for area accumulation
        self._queue_vars = [sv for sv in self._state_var_names
                           if sv.startswith("queue_count") or re.match(r'^Q\d', sv)]

        # Parse random streams
        for stream_name, stream_def in spec.get("random_streams", {}).items():
            dist = stream_def["distribution"]
            params = {}
            for pk, pv in stream_def.get("params", {}).items():
                # Resolve parameter references
                if isinstance(pv, str) and pv in self._params:
                    params[pk] = self._params[pv]
                else:
                    params[pk] = pv
            self._random_streams[stream_name] = (dist, params)

        # Parse vertices
        for v in spec.get("vertices", []):
            name = v["name"]
            self._vertex_map[name] = v

        # Parse scheduling edges, indexed by source vertex
        for v_name in self._vertex_map:
            self._edges_from[v_name] = []
        for edge in spec.get("scheduling_edges", []):
            self._edges_from[edge["from"]].append(edge)

        # Parse feedback_prob if present
        self._feedback_prob = self._params.get("feedback_prob", 0.5)

        # Schedule initial events
        for init_ev in spec.get("initial_events", []):
            event_name = init_ev["event"]
            delay_spec = init_ev.get("time", 0)
            delay = self._resolve_delay(delay_spec)
            self.schedule(lambda name=event_name: self._fire_event(name),
                         timedelta(hours=delay))

    @classmethod
    def from_json(cls, json_path, seed: int = 0):
        """Create an EventGraphModel from a JSON file path.

        Args:
            json_path: Path to EG JSON specification file.
            seed: Random seed.

        Returns:
            Configured EventGraphModel instance.
        """
        path = Path(json_path)
        with open(path, "r", encoding="utf-8") as f:
            spec = json.load(f)
        return cls(spec, seed=seed)

    # -----------------------------------------------------------------
    # Event execution
    # -----------------------------------------------------------------

    def _fire_event(self, event_name: str):
        """Fire an event vertex: execute state changes, then process edges."""
        self._update_areas()

        vertex = self._vertex_map[event_name]

        # Execute state changes
        state_change = vertex.get("state_change", "")
        if state_change:
            self._execute_state_changes(state_change)

        # Update in_system from observables expression
        self._update_in_system()

        # Check if this vertex has feedback/not_feedback edges (mutually exclusive)
        edges = self._edges_from[event_name]
        has_feedback = any(e.get("condition") in ("feedback", "not_feedback")
                          for e in edges)

        if has_feedback:
            # Draw once for this vertex's feedback decision
            feedback_roll = random.random()
            for edge in edges:
                cond = edge.get("condition", "true")
                if cond == "feedback":
                    if feedback_roll < self._feedback_prob:
                        self._process_edge_unconditional(edge)
                elif cond == "not_feedback":
                    if feedback_roll >= self._feedback_prob:
                        self._process_edge_unconditional(edge)
                else:
                    self._process_edge(edge)
        else:
            for edge in edges:
                self._process_edge(edge)

    def _process_edge(self, edge: dict):
        """Evaluate edge condition and schedule target event if true."""
        condition = edge.get("condition", "true")
        target = edge["to"]
        delay_spec = edge.get("delay", 0)

        # Normal condition evaluation (feedback handled in _fire_event)
        if condition == "true" or self._evaluate_condition(condition):
            delay = self._resolve_delay(delay_spec)
            self.schedule(
                lambda name=target: self._fire_event(name),
                timedelta(hours=delay))

    def _process_edge_unconditional(self, edge: dict):
        """Schedule target event unconditionally (feedback decision already made).

        Note: feedback_action/depart_action edge fields are NOT executed here —
        they are SimASM metadata. The target vertex's state_change handles
        the necessary state updates (e.g., departure_count increment in Depart,
        queue_count_1 increment in Start_1 via Arrive-like logic).
        However, the feedback path needs queue_count_1 incremented before
        the target event fires, since the JSON spec encodes this in
        feedback_action. We execute feedback_action only.
        """
        target = edge["to"]
        delay_spec = edge.get("delay", 0)

        # feedback_action is needed (e.g., "queue_count_1 := queue_count_1 + 1")
        # because the target vertex (Start_1) doesn't do this itself.
        # depart_action is NOT needed because Depart vertex already increments.
        feedback_action = edge.get("feedback_action", "")
        if feedback_action:
            self._execute_state_changes(feedback_action)

        delay = self._resolve_delay(delay_spec)
        self.schedule(
            lambda name=target: self._fire_event(name),
            timedelta(hours=delay))

    # -----------------------------------------------------------------
    # State change execution
    # -----------------------------------------------------------------

    def _execute_state_changes(self, state_change_str: str):
        """Execute semicolon-separated assignment statements.

        Format: "var := expr; var2 := expr2"
        """
        assignments = [s.strip() for s in state_change_str.split(";")
                       if s.strip()]
        for assignment in assignments:
            if ":=" not in assignment:
                continue
            lhs, rhs = assignment.split(":=", 1)
            lhs = lhs.strip()
            rhs = rhs.strip()
            value = self._evaluate_expr(rhs)
            setattr(self, lhs, value)

    def _evaluate_expr(self, expr: str):
        """Evaluate an expression in the context of state variables and params."""
        # Build evaluation namespace
        ns = {}
        for sv_name in self._state_var_names:
            ns[sv_name] = getattr(self, sv_name)
        for pname, pval in self._params.items():
            ns[pname] = pval
        # Replace common tokens
        expr_py = expr.strip()
        try:
            return eval(expr_py, {"__builtins__": {}}, ns)
        except Exception:
            return 0

    def _evaluate_condition(self, condition: str) -> bool:
        """Evaluate a boolean condition expression."""
        if condition == "true":
            return True
        if condition == "false":
            return False
        ns = {}
        for sv_name in self._state_var_names:
            ns[sv_name] = getattr(self, sv_name)
        for pname, pval in self._params.items():
            ns[pname] = pval
        try:
            return bool(eval(condition, {"__builtins__": {}}, ns))
        except Exception:
            return False

    # -----------------------------------------------------------------
    # Random variate generation
    # -----------------------------------------------------------------

    def _resolve_delay(self, delay_spec) -> float:
        """Resolve a delay specification to a float value (hours).

        delay_spec can be:
          - int/float: constant delay
          - str: name of a random stream
        """
        if isinstance(delay_spec, (int, float)):
            return float(delay_spec)
        if isinstance(delay_spec, str):
            if delay_spec in self._random_streams:
                return self._sample_stream(delay_spec)
            # Try as parameter reference
            if delay_spec in self._params:
                return float(self._params[delay_spec])
        return 0.0

    def _sample_stream(self, stream_name: str) -> float:
        """Sample from a random stream."""
        dist, params = self._random_streams[stream_name]
        if dist == "exponential":
            mean = params.get("mean", 1.0)
            return random.expovariate(1.0 / mean)
        elif dist == "uniform":
            low = params.get("low", 0.0)
            high = params.get("high", 1.0)
            return random.uniform(low, high)
        elif dist == "constant":
            return params.get("value", 0.0)
        return 0.0

    # -----------------------------------------------------------------
    # Area accumulators and in_system tracking
    # -----------------------------------------------------------------

    def _update_areas(self):
        """Update time-weighted area accumulators."""
        now = self.clock_time
        if self._last_event_time is not None:
            dt = (now - self._last_event_time).total_seconds() / 3600.0
            if dt > 0:
                q_total = sum(getattr(self, qv) for qv in self._queue_vars)
                self._area_queue_total += q_total * dt
                self._area_system += self.in_system * dt
        self._last_event_time = now

    def _update_in_system(self):
        """Update in_system from state variables."""
        if self._in_system_expr:
            self.in_system = self._evaluate_expr(self._in_system_expr)
        else:
            total = 0
            for sv in self._state_var_names:
                if (sv.startswith("queue_count") or sv.startswith("server_count")
                        or sv.startswith("part_")):
                    total += getattr(self, sv)
                elif re.match(r'^Q\d', sv):
                    total += getattr(self, sv)
                elif re.match(r'^S\d', sv):
                    cap_param = f"{sv}_capacity"
                    if cap_param in self._params:
                        total += self._params[cap_param] - getattr(self, sv)
            self.in_system = total

    def get_departure_count(self):
        """Return departure count, checking both 'departure_count' and 'departures'."""
        if hasattr(self, "departures"):
            return self.departures
        return getattr(self, "departure_count", 0)
