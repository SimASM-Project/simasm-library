"""
Event Graph to SimASM Converter

Converts Event Graph specifications in algebraic format to SimASM code.
Based on the Next-Event Time-Advance Algorithm from Law (2013).

The algebraic specification S = (F, C, T, Γ, G) maps to SimASM as:
    F (state transitions) → Event rules with assignment statements
    C (edge conditions)   → Boolean predicates for conditional scheduling
    T (edge delays)       → Random stream samples or constants
    Γ (priorities)        → Event scheduling priority values
    G (graph structure)   → Event types and scheduling edges

Algorithm flow:
1. Initialization: Set clock=0, STATE=STATE_0, FEL=FEL_0
2. Timing: Pop earliest event from FEL, advance clock
3. Event routine: Execute f_v, process scheduling edges with c_e and t_e
4. Repeat until termination condition

References:
- Schruben (1983) Event Graph methodology
- Law (2013) Next-Event Time-Advance Algorithm
"""

import re
from typing import List, Dict, Optional, Tuple
from io import StringIO
from datetime import datetime

from .schema import (
    EventGraphSpec, VertexSpec, SchedulingEdgeSpec, CancellingEdgeSpec,
    StateVariableSpec, ParameterSpec, RandomStreamSpec, ObservableSpec,
    load_eg_from_json
)


class SimASMPrettyPrinter:
    """Helper for generating formatted SimASM code."""

    def __init__(self):
        self.buffer = StringIO()
        self.indent_level = 0
        self.indent_str = "    "

    def write(self, text: str):
        """Write text with current indentation."""
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if line.strip():
                self.buffer.write(self.indent_str * self.indent_level + line)
            if i < len(lines) - 1:
                self.buffer.write('\n')

    def writeln(self, text: str = ""):
        """Write text with newline."""
        self.write(text)
        self.buffer.write('\n')

    def blank(self):
        """Write blank line."""
        self.buffer.write('\n')

    def indent(self):
        """Increase indentation."""
        self.indent_level += 1

    def dedent(self):
        """Decrease indentation."""
        self.indent_level = max(0, self.indent_level - 1)

    def comment(self, text: str):
        """Write a comment line."""
        self.writeln(f"// {text}")

    def section_comment(self, title: str, char: str = "=", width: int = 77):
        """Write a section header comment."""
        self.writeln(f"// {char * width}")
        self.writeln(f"// {title}")
        self.writeln(f"// {char * width}")

    def subsection_comment(self, title: str, char: str = "-", width: int = 77):
        """Write a subsection header comment."""
        self.writeln(f"// {char * width}")
        self.writeln(f"// {title}")
        self.writeln(f"// {char * width}")

    def get_output(self) -> str:
        """Get the generated code."""
        return self.buffer.getvalue()


def to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


class EventGraphConverter:
    """
    Converts Event Graph v2 specification to SimASM code.

    Implements the Next-Event Time-Advance Algorithm:
    1. Initialization routine: Set STATE_0 and schedule FEL_0
    2. Timing routine: Pop next event, advance clock
    3. Event routine: Execute state transition f_v
    4. Scheduling: For each edge (v,w), if c_e then schedule w at t+t_e

    Generated code structure:
    1. Header and imports
    2. Domain declarations (Event types)
    3. Constants (parameters)
    4. Variables (state variables, sim_clocktime, FEL)
    5. Random streams
    6. Dynamic functions (event properties)
    7. Derived functions (observables)
    8. Rules (event_* for each vertex)
    9. Algorithm rules (timing_routine, event_routine)
    10. Init block
    11. Main rule
    """

    def __init__(self, spec: EventGraphSpec):
        self.spec = spec
        self.pp = SimASMPrettyPrinter()

    def convert(self) -> str:
        """Convert the Event Graph spec to SimASM code."""
        self._write_header()
        self._write_imports()
        self._write_domains()
        self._write_constants()
        self._write_variables()
        self._write_random_streams()
        self._write_dynamic_functions()
        self._write_derived_functions()
        self._write_event_rules()
        self._write_algorithm_rules()
        self._write_init_block()
        self._write_main_rule()

        return self.pp.get_output()

    # =========================================================================
    # HEADER AND IMPORTS
    # =========================================================================

    def _write_header(self):
        """Write the file header."""
        self.pp.section_comment(f"Event Graph Model: {self.spec.model_name}")
        if self.spec.description:
            for line in self.spec.description.split('\n'):
                self.pp.comment(line)
        self.pp.comment(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.pp.comment("Formalism: Event Graph (Schruben 1983)")
        self.pp.comment("Algorithm: Next-Event Time-Advance (Law 2013)")
        self.pp.blank()

    def _write_imports(self):
        """Write import declarations."""
        self.pp.section_comment("IMPORT LIBRARIES")
        self.pp.blank()
        self.pp.writeln("import Random as rnd")
        self.pp.writeln("import Stdlib as lib")
        self.pp.blank()

    # =========================================================================
    # DOMAIN DECLARATIONS
    # =========================================================================

    def _write_domains(self):
        """Write domain declarations."""
        self.pp.section_comment("DOMAIN DECLARATIONS")
        self.pp.blank()

        self.pp.comment("Base object domain")
        self.pp.writeln("domain Object")
        self.pp.blank()

        self.pp.comment("Event domain")
        self.pp.writeln("domain Event")
        self.pp.blank()

    # =========================================================================
    # CONSTANTS
    # =========================================================================

    def _write_constants(self):
        """Write constant declarations."""
        self.pp.section_comment("CONSTANT DECLARATIONS")
        self.pp.blank()

        for name, param in self.spec.parameters.items():
            type_str = param.type if param.type else "Nat"
            comment = f"  // {param.description}" if param.description else ""
            self.pp.writeln(f"const {name}: {type_str}{comment}")

        self.pp.blank()

    # =========================================================================
    # VARIABLES - STATES space
    # =========================================================================

    def _write_variables(self):
        """Write variable declarations for STATES space."""
        self.pp.section_comment("DYNAMIC VARIABLE DECLARATIONS - STATES space")
        self.pp.blank()

        self.pp.comment("Simulation clock and event list")
        self.pp.writeln("var sim_clocktime: Real")
        self.pp.writeln("var future_event_list: List<Event>")
        self.pp.writeln("var current_event: Event")
        self.pp.blank()

        self.pp.comment("State variables (STATES)")
        for name, var in self.spec.state_variables.items():
            type_str = var.type if var.type else "Nat"
            comment = f"  // {var.description}" if var.description else ""
            self.pp.writeln(f"var {name}: {type_str}{comment}")

        self.pp.blank()

    # =========================================================================
    # RANDOM STREAMS - Delay functions T
    # =========================================================================

    def _write_random_streams(self):
        """Write random stream declarations for edge delays T."""
        self.pp.section_comment("RANDOM STREAM VARIABLES - Edge delay functions T")
        self.pp.blank()

        for name, stream in self.spec.random_streams.items():
            dist = stream.distribution
            params = stream.params
            param_str = ", ".join(str(v) for v in params.values())

            if stream.stream_name:
                self.pp.writeln(f'var {name}: rnd.{dist}({param_str}) as "{stream.stream_name}"')
            else:
                self.pp.writeln(f"var {name}: rnd.{dist}({param_str})")

        self.pp.blank()

    # =========================================================================
    # DYNAMIC FUNCTIONS
    # =========================================================================

    def _write_dynamic_functions(self):
        """Write dynamic function declarations."""
        self.pp.section_comment("DYNAMIC FUNCTION DECLARATIONS")
        self.pp.blank()

        self.pp.comment("Event properties")
        self.pp.writeln("dynamic function event_rule(e: Event): Rule")
        self.pp.writeln("dynamic function event_scheduled_time(e: Event): Real")
        self.pp.writeln("dynamic function event_parameters(e: Event): List<Any>")
        self.pp.blank()

    # =========================================================================
    # DERIVED FUNCTIONS - Observables
    # =========================================================================

    def _write_derived_functions(self):
        """Write derived function declarations for observables."""
        if not self.spec.observables:
            return

        self.pp.section_comment("DERIVED FUNCTIONS - Observables")
        self.pp.blank()

        for name, obs in self.spec.observables.items():
            return_type = obs.return_type if obs.return_type else "Nat"
            expr = obs.expression
            comment = f"  // {obs.description}" if obs.description else ""

            self.pp.writeln(f"derived function {name}(): {return_type} ={comment}")
            self.pp.indent()
            self.pp.writeln(expr)
            self.pp.dedent()
            self.pp.blank()

    # =========================================================================
    # EVENT RULES - State transition functions F
    # =========================================================================

    def _write_event_rules(self):
        """Write event rules implementing state transition functions F."""
        self.pp.section_comment("EVENT RULES - State transition functions F")
        self.pp.blank()

        for vertex in self.spec.vertices:
            self._write_event_rule(vertex)

    def _write_event_rule(self, vertex: VertexSpec):
        """Write a single event rule for vertex v with f_v."""
        rule_name = f"event_{to_snake_case(vertex.name)}"

        self.pp.subsection_comment(f"{vertex.name} Event - f_{vertex.name}")
        if vertex.description:
            self.pp.comment(vertex.description)
        self.pp.blank()

        self.pp.writeln(f"rule {rule_name}() =")
        self.pp.indent()

        # Parse and write state transition f_v
        if vertex.state_change:
            self.pp.comment(f"State transition: {vertex.state_change}")
            self._write_state_change(vertex.state_change)
            self.pp.blank()

        # Get outgoing scheduling edges
        outgoing_edges = [e for e in self.spec.scheduling_edges if e.source == vertex.name]

        if outgoing_edges:
            self.pp.comment("Process scheduling edges E_s(G)")
            for edge in outgoing_edges:
                self._write_edge_scheduling(edge)

        # Get outgoing cancelling edges
        cancelling_edges = [e for e in self.spec.cancelling_edges if e.source == vertex.name]

        if cancelling_edges:
            self.pp.comment("Process cancelling edges E_c(G)")
            for edge in cancelling_edges:
                self._write_edge_cancelling(edge)

        self.pp.dedent()
        self.pp.writeln("endrule")
        self.pp.blank()

    def _write_state_change(self, state_change: str):
        """
        Parse and write state change assignments.

        Input format: "q := q + 1; p := p - 1"
        Output: SimASM assignment statements
        """
        if not state_change.strip():
            return

        # Split by semicolon for multiple assignments
        assignments = [a.strip() for a in state_change.split(";") if a.strip()]

        for assignment in assignments:
            # Parse "var := expr"
            if ":=" in assignment:
                parts = assignment.split(":=", 1)
                var_name = parts[0].strip()
                expr = parts[1].strip()
                self.pp.writeln(f"{var_name} := {expr}")

    def _write_edge_scheduling(self, edge: SchedulingEdgeSpec):
        """
        Write scheduling code for edge e = (v, w).

        Implements: if c_e(STATE) then schedule w at t + t_e with priority γ_e
        """
        target_rule = f"event_{to_snake_case(edge.target)}"
        event_var = f"scheduled_{to_snake_case(edge.target)}"

        # Check condition c_e
        condition = edge.condition.strip().lower() if edge.condition else "true"
        has_condition = condition != "true"

        if edge.description:
            self.pp.comment(edge.description)

        if has_condition:
            self.pp.writeln(f"if {edge.condition} then")
            self.pp.indent()

        # Create and schedule event
        self.pp.writeln(f"let {event_var} = new Event")

        # Set event_rule for dispatch
        self.pp.writeln(f'event_rule({event_var}) := "{target_rule}"')

        # Set scheduled time: t + t_e
        delay = edge.delay
        if isinstance(delay, (int, float)):
            if delay == 0:
                self.pp.writeln(f"event_scheduled_time({event_var}) := sim_clocktime")
            else:
                self.pp.writeln(f"event_scheduled_time({event_var}) := sim_clocktime + {delay}")
        else:
            # Random stream or expression
            self.pp.writeln(f"event_scheduled_time({event_var}) := sim_clocktime + {delay}")

        # Set parameters (empty for v2 simple model)
        self.pp.writeln(f"event_parameters({event_var}) := []")

        # Add to FEL
        self.pp.writeln(f"lib.add(future_event_list, {event_var})")

        if has_condition:
            self.pp.dedent()
            self.pp.writeln("endif")

        self.pp.blank()

    def _write_edge_cancelling(self, edge: CancellingEdgeSpec):
        """Write cancelling code for edge e = (v, w)."""
        condition = edge.condition.strip().lower() if edge.condition else "true"
        has_condition = condition != "true"

        self.pp.comment(f"Cancel pending {edge.target} events")

        if has_condition:
            self.pp.writeln(f"if {edge.condition} then")
            self.pp.indent()

        # Remove matching events from FEL
        self.pp.writeln(f"// TODO: Remove {edge.target}Event instances from future_event_list")

        if has_condition:
            self.pp.dedent()
            self.pp.writeln("endif")

        self.pp.blank()

    # =========================================================================
    # ALGORITHM RULES - Next-Event Time-Advance
    # =========================================================================

    def _write_algorithm_rules(self):
        """Write the Next-Event Time-Advance Algorithm rules."""
        self.pp.section_comment("NEXT-EVENT TIME-ADVANCE ALGORITHM")
        self.pp.blank()

        self._write_initialization_routine()
        self._write_timing_routine()
        self._write_event_routine()

    def _write_initialization_routine(self):
        """Write initialization routine: STATE := STATE_0, FEL := FEL_0."""
        self.pp.subsection_comment("Initialization Routine")
        self.pp.comment("Set STATE := STATE_0, FEL := FEL_0")
        self.pp.blank()

        self.pp.writeln("rule initialisation_routine() =")
        self.pp.indent()

        # Schedule initial events (FEL_0)
        for i, init_event in enumerate(self.spec.initial_events):
            event_var = f"init_event_{i}"

            rule_name = f"event_{to_snake_case(init_event.event)}"

            self.pp.comment(f"Schedule initial {init_event.event} event")
            self.pp.writeln(f"let {event_var} = new Event")
            self.pp.writeln(f'event_rule({event_var}) := "{rule_name}"')

            # Set scheduled time
            time = init_event.time
            if isinstance(time, (int, float)):
                self.pp.writeln(f"event_scheduled_time({event_var}) := {float(time)}")
            else:
                # String delay (e.g., "T_a") - add sim_clocktime offset
                self.pp.writeln(f"event_scheduled_time({event_var}) := sim_clocktime + {time}")

            self.pp.writeln(f"event_parameters({event_var}) := []")
            self.pp.writeln(f"lib.add(future_event_list, {event_var})")
            self.pp.blank()

        self.pp.dedent()
        self.pp.writeln("endrule")
        self.pp.blank()

    def _write_timing_routine(self):
        """Write timing routine: pop next event, advance clock."""
        self.pp.subsection_comment("Timing Routine")
        self.pp.comment("Pop earliest event from FEL, advance clock to event time")
        self.pp.blank()

        self.pp.writeln("rule timing_routine() =")
        self.pp.indent()

        self.pp.comment("Sort FEL by (scheduled_time, -priority)")
        self.pp.writeln('lib.sort(future_event_list, "event_scheduled_time")')
        self.pp.blank()

        self.pp.writeln("if lib.length(future_event_list) > 0 then")
        self.pp.indent()

        self.pp.comment("Remove next event from FEL")
        self.pp.writeln("let next_event = lib.pop(future_event_list)")
        self.pp.blank()

        self.pp.comment("Advance simulation clock")
        self.pp.writeln("sim_clocktime := event_scheduled_time(next_event)")
        self.pp.blank()

        self.pp.comment("Store for event routine dispatch")
        self.pp.writeln("current_event := next_event")

        self.pp.dedent()
        self.pp.writeln("endif")

        self.pp.dedent()
        self.pp.writeln("endrule")
        self.pp.blank()

    def _write_event_routine(self):
        """Write event routine: dispatch to appropriate event rule."""
        self.pp.subsection_comment("Event Routine")
        self.pp.comment("Dispatch to event-specific rule using lib.apply_rule")
        self.pp.blank()

        self.pp.writeln("rule event_routine() =")
        self.pp.indent()

        # Use lib.apply_rule for dispatch (matches existing EG models)
        self.pp.writeln("let r = event_rule(current_event)")
        self.pp.writeln("let params = event_parameters(current_event)")
        self.pp.writeln("lib.apply_rule(r, params)")

        self.pp.dedent()
        self.pp.writeln("endrule")
        self.pp.blank()

    # =========================================================================
    # INIT BLOCK - STATE_0
    # =========================================================================

    def _write_init_block(self):
        """Write initialization block for STATE_0."""
        self.pp.section_comment("INITIAL STATE - STATE_0")
        self.pp.blank()

        self.pp.writeln("init:")
        self.pp.indent()

        # Parameters
        self.pp.comment("Parameters")
        for name, param in self.spec.parameters.items():
            value = param.value
            if isinstance(value, float):
                self.pp.writeln(f"{name} := {value}")
            elif isinstance(value, bool):
                self.pp.writeln(f"{name} := {str(value).lower()}")
            else:
                self.pp.writeln(f"{name} := {value}")
        self.pp.blank()

        # Simulation state
        self.pp.comment("Simulation state")
        self.pp.writeln("sim_clocktime := 0.0")
        self.pp.writeln("future_event_list := []")
        self.pp.blank()

        # State variables (STATES_0)
        self.pp.comment("Initial state variables STATE_0")
        for name, var in self.spec.state_variables.items():
            initial = var.initial
            if isinstance(initial, float):
                self.pp.writeln(f"{name} := {initial}")
            elif isinstance(initial, bool):
                self.pp.writeln(f"{name} := {str(initial).lower()}")
            else:
                self.pp.writeln(f"{name} := {initial}")

        self.pp.dedent()
        self.pp.writeln("endinit")
        self.pp.blank()

    # =========================================================================
    # MAIN RULE
    # =========================================================================

    def _write_main_rule(self):
        """Write main simulation loop."""
        self.pp.section_comment("MAIN RULE")
        self.pp.blank()

        self.pp.writeln("main rule main =")
        self.pp.indent()

        # Initialize on first step
        self.pp.comment("Initialize on first step")
        self.pp.writeln("if sim_clocktime == 0.0 and lib.length(future_event_list) == 0 then")
        self.pp.indent()
        self.pp.writeln("initialisation_routine()")
        self.pp.dedent()
        self.pp.writeln("endif")
        self.pp.blank()

        # Main simulation loop
        self.pp.comment("Run while FEL not empty and time not exceeded")
        self.pp.writeln("if lib.length(future_event_list) > 0 and sim_clocktime < sim_end_time then")
        self.pp.indent()
        self.pp.writeln("timing_routine()")
        self.pp.writeln("event_routine()")
        self.pp.dedent()
        self.pp.writeln("endif")

        self.pp.dedent()
        self.pp.writeln("endrule")
        self.pp.blank()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def convert_eg(spec: EventGraphSpec) -> str:
    """Convert an Event Graph v2 specification to SimASM code."""
    converter = EventGraphConverter(spec)
    return converter.convert()


def convert_eg_from_json(json_path: str) -> str:
    """Load Event Graph v2 JSON and convert to SimASM code."""
    spec = load_eg_from_json(json_path)
    return convert_eg(spec)
