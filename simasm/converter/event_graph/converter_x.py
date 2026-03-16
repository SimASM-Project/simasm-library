"""
Pure Event Graph to SimASM Converter

Converts Pure Event Graph JSON specifications (without SimASM syntax) to SimASM code.
All SimASM code generation happens in this translator layer.

Implements the next-event time-advance algorithm as described in
"Event Graph Formalism with Abstract State Machine".
"""

import re
from typing import List, Dict, Any, Optional, Union
from .schema import (
    PureEventGraphSpec, PureVertexSpec, PureSchedulingEdgeSpec, PureCancellingEdgeSpec,
    EntitySpec, StateVariableSpec, ParameterSpec, RandomStreamSpec,
    ObservableSpec, ResourceSpec, PredicateSpec, ParamSpec,
    StateChangeOp, ConditionSpec,
    IncrementOp, DecrementOp, SetOp, CreateEntityOp, SetAttributeOp,
    AddToListOp, RemoveFromListOp, IncrementCounterOp, DecrementCounterOp,
    AccumulateOp, ComputeOp,
    CompareCondition, ListLengthCondition, AndCondition, OrCondition, TrueCondition,
    EntityParamSpec, FirstFromListParamSpec
)
from ..codegen.pretty_printer import PrettyPrinter
from ..codegen.ast_builder import ASTBuilder


def to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


class PureEventGraphConverter:
    """
    Converts Pure Event Graph specifications to SimASM code.

    All SimASM syntax generation happens here, not in the JSON spec.
    """

    def __init__(self, spec: PureEventGraphSpec):
        self.spec = spec
        self.pp = PrettyPrinter()
        self.builder = ASTBuilder()

    def convert(self) -> str:
        """Convert the specification to SimASM code."""
        self.pp.reset()

        self._write_header()
        self._write_imports()
        self._write_domains()
        self._write_constants()
        self._write_variables()
        self._write_random_streams()
        self._write_static_functions()
        self._write_dynamic_functions()
        self._write_derived_functions()
        self._write_rules()
        self._write_init_block()
        self._write_main_rule()

        return self.pp.get_output()

    # =========================================================================
    # SIMASM CODE GENERATION FROM ABSTRACT OPERATIONS
    # =========================================================================

    def _translate_state_change(self, op: StateChangeOp) -> List[str]:
        """Translate an abstract state change operation to SimASM code lines."""
        lines = []

        if isinstance(op, IncrementOp):
            if op.amount == 1:
                lines.append(f"{op.var} := {op.var} + 1")
            else:
                lines.append(f"{op.var} := {op.var} + {op.amount}")

        elif isinstance(op, DecrementOp):
            if op.amount == 1:
                lines.append(f"{op.var} := {op.var} - 1")
            else:
                lines.append(f"{op.var} := {op.var} - {op.amount}")

        elif isinstance(op, SetOp):
            lines.append(f"{op.var} := {op.value}")

        elif isinstance(op, CreateEntityOp):
            lines.append(f"let {op.as_var} = new {op.entity_type}")

        elif isinstance(op, SetAttributeOp):
            lines.append(f"{op.attribute}({op.entity}) := {op.value}")

        elif isinstance(op, AddToListOp):
            lines.append(f"lib.add({op.list_name}({op.resource}), {op.entity})")

        elif isinstance(op, RemoveFromListOp):
            lines.append(f"lib.remove({op.list_name}({op.resource}), {op.entity})")

        elif isinstance(op, IncrementCounterOp):
            counter_expr = f"{op.counter}({op.resource})"
            if op.amount == 1:
                lines.append(f"{counter_expr} := {counter_expr} + 1")
            else:
                lines.append(f"{counter_expr} := {counter_expr} + {op.amount}")

        elif isinstance(op, DecrementCounterOp):
            counter_expr = f"{op.counter}({op.resource})"
            if op.amount == 1:
                lines.append(f"{counter_expr} := {counter_expr} - 1")
            else:
                lines.append(f"{counter_expr} := {counter_expr} - {op.amount}")

        elif isinstance(op, AccumulateOp):
            acc_expr = f"{op.accumulator}({op.resource})"
            lines.append(f"{acc_expr} := {acc_expr} + {op.value}")

        elif isinstance(op, ComputeOp):
            lines.append(f"let {op.var} = {op.expression}")

        return lines

    def _translate_condition(self, cond: Union[ConditionSpec, str]) -> str:
        """Translate an abstract condition to SimASM boolean expression."""
        if isinstance(cond, str):
            # Handle probabilistic branching shorthand
            if cond == "not_feedback":
                return "not feedback"
            return cond  # Already a string like "true"

        if isinstance(cond, TrueCondition) or cond == "true":
            return "true"

        if isinstance(cond, CompareCondition):
            return f"{cond.left} {cond.operator} {cond.right}"

        if isinstance(cond, ListLengthCondition):
            left = f"lib.length({cond.list_name}({cond.resource}))"
            return f"{left} {cond.operator} {cond.value}"

        if isinstance(cond, AndCondition):
            parts = [self._translate_condition(c) for c in cond.conditions]
            return " and ".join(parts)

        if isinstance(cond, OrCondition):
            parts = [self._translate_condition(c) for c in cond.conditions]
            return " or ".join(f"({p})" for p in parts)

        return "true"

    def _translate_parameter(self, param: ParamSpec) -> str:
        """Translate an abstract parameter specification to SimASM expression."""
        if isinstance(param, EntityParamSpec):
            return param.var

        if isinstance(param, FirstFromListParamSpec):
            return f"lib.first({param.list_name}({param.resource}))"

        return str(param)

    # =========================================================================
    # SECTION GENERATORS
    # =========================================================================

    def _write_header(self):
        """Write the file header."""
        self.pp.write_header(
            self.spec.model_name,
            self.spec.description,
            formalism="Event Graph"
        )

    def _write_imports(self):
        """Write import declarations."""
        self.pp.write_imports()

    def _write_domains(self):
        """Write domain declarations."""
        self.pp.block_comment("DOMAIN DECLARATIONS")
        self.pp.blank()

        self.pp.write_domain("Object")

        # Resource domains
        for name, resource in self.spec.resources.items():
            self.pp.write_domain(resource.type, "Object")

        # Entity domains
        for name, entity in self.spec.entities.items():
            self.pp.write_domain(name, entity.parent)

        # Event domain hierarchy
        self.pp.blank()
        self.pp.comment("Event domain hierarchy")
        self.pp.write_domain("Event", "Object")
        for vertex in self.spec.vertices:
            self.pp.write_domain(f"{vertex.name}Event", "Event")

        self.pp.blank()

    def _write_constants(self):
        """Write constant declarations."""
        self.pp.block_comment("CONSTANT DECLARATIONS (Static 0-ary Functions)")
        self.pp.blank()

        # Resource singletons
        for name, resource in self.spec.resources.items():
            self.pp.write_const(name, resource.type)
        self.pp.blank()

        # Model parameters
        for name, param in self.spec.parameters.items():
            type_str = self.builder.map_variable_type(param.type)
            self.pp.write_const(name, type_str, param.description)

        self.pp.blank()

    def _write_variables(self):
        """Write variable declarations."""
        self.pp.block_comment("DYNAMIC VARIABLE DECLARATIONS (Dynamic 0-ary Functions)")
        self.pp.blank()

        # Core simulation variables
        self.pp.write_var("future_event_list", "List<Event>")
        self.pp.write_var("sim_clocktime", "Real")
        self.pp.write_var("current_event", "Event")

        # State variables
        for name, var in self.spec.state_variables.items():
            type_str = self.builder.map_variable_type(var.type)
            self.pp.write_var(name, type_str, var.description)

        self.pp.blank()

    def _write_random_streams(self):
        """Write random stream declarations."""
        self.pp.block_comment("RANDOM STREAM VARIABLES")
        self.pp.blank()

        for name, stream in self.spec.random_streams.items():
            dist = self.builder.map_distribution(stream.distribution)
            self.pp.write_random_stream(name, dist, stream.params, stream.stream_name)

        self.pp.blank()

    def _write_static_functions(self):
        """Write static function declarations."""
        self.pp.block_comment("STATIC FUNCTION DECLARATIONS")
        self.pp.blank()

        self.pp.write_static_func("id", [("obj", "Object")], "Nat")
        self.pp.blank()

    def _write_dynamic_functions(self):
        """Write dynamic function declarations."""
        self.pp.block_comment("DYNAMIC FUNCTION DECLARATIONS")
        self.pp.blank()

        # Entity attributes
        for entity_name, entity in self.spec.entities.items():
            if entity.attributes:
                self.pp.comment(f"{entity_name} attributes")
                for attr_name, attr_type in entity.attributes.items():
                    type_str = attr_type if isinstance(attr_type, str) else self.builder.map_variable_type(attr_type)
                    self.pp.write_dynamic_func(attr_name, [("l", entity_name)], type_str)
                self.pp.blank()

        # Resource accumulators
        has_accumulators = False
        for res_name, resource in self.spec.resources.items():
            if resource.accumulators:
                has_accumulators = True
                for acc_name in resource.accumulators:
                    self.pp.write_dynamic_func(acc_name, [("s", resource.type)], "Real")
        if has_accumulators:
            self.pp.blank()

        # Resource lists
        self.pp.comment("Entity lists")
        for res_name, resource in self.spec.resources.items():
            for list_name in resource.lists:
                entity_type = list(self.spec.entities.keys())[0] if self.spec.entities else "Object"
                self.pp.write_dynamic_func(list_name, [(res_name[0], resource.type)], f"List<{entity_type}>")
        self.pp.blank()

        # Resource counters
        self.pp.comment("Counters")
        for res_name, resource in self.spec.resources.items():
            for counter_name in resource.counters:
                self.pp.write_dynamic_func(counter_name, [(res_name[0], resource.type)], "Nat")
        self.pp.blank()

        # Event properties
        self.pp.comment("Event properties (stored as dynamic functions)")
        self.pp.write_dynamic_func("event_rule", [("e", "Event")], "Rule")
        self.pp.write_dynamic_func("event_scheduled_time", [("e", "Event")], "Real")
        self.pp.write_dynamic_func("event_parameters", [("e", "Event")], "List<Any>")
        self.pp.blank()

    def _write_derived_functions(self):
        """Write derived function declarations.

        Note: Only writes observables. Predicates for verification are defined
        in verification specification files, not in the model.
        """
        if not self.spec.observables:
            return

        self.pp.section_comment("Observable State Derived Functions")
        self.pp.comment("These wrap the dynamic function accessors for cleaner syntax")
        self.pp.blank()

        # Write observables only (predicates are defined in verification files)
        for name, obs in self.spec.observables.items():
            return_type = getattr(obs, 'return_type', 'Nat')
            # Translate observable expression to SimASM
            expr = self._translate_observable_expression(obs.expression)
            self.pp.write_derived_func(obs.name, [], return_type, expr)
            self.pp.blank()

    def _translate_observable_expression(self, expr: str) -> str:
        """Translate observable expression references."""
        # Map abstract references to SimASM
        # e.g., "queue.count" -> "queue_count(queue)"
        # For now, just return as-is if already in correct format
        return expr

    def _write_rules(self):
        """Write all rules."""
        self.pp.block_comment("RULES")
        self.pp.blank()

        self._write_initialization_routine()
        self._write_timing_routine()
        self._write_event_routine()
        self._write_run_routine()

        for vertex in self.spec.vertices:
            self._write_event_rule(vertex)

    def _write_initialization_routine(self):
        """Write the initialization routine."""
        self.pp.section_comment("Initialization Routine")
        self.pp.blank()

        self.pp.write_rule_start("initialisation_routine")

        for i, init_event in enumerate(self.spec.initial_events):
            vertex = self.spec.get_vertex(init_event.event)
            if vertex:
                event_type = f"{init_event.event}Event"
                self.pp.write_new(f"init_event_{i}", event_type)
                self.pp.write_update(f"event_rule(init_event_{i})", f'"{to_snake_case(init_event.event)}"')
                time_expr = str(init_event.time) if isinstance(init_event.time, (int, float)) else init_event.time
                self.pp.write_update(f"event_scheduled_time(init_event_{i})", f"sim_clocktime + {time_expr}")
                self.pp.write_update(f"event_parameters(init_event_{i})", "[]")
                self.pp.write_lib_call("add", "future_event_list", f"init_event_{i}")
                self.pp.blank()

        self.pp.write_rule_end()
        self.pp.blank()

    def _write_timing_routine(self):
        """Write the timing routine."""
        self.pp.section_comment("Timing Routine")
        self.pp.blank()

        self.pp.write_rule_start("timing_routine")

        self.pp.comment("Sort FEL by scheduled time")
        self.pp.write_lib_call("sort", "future_event_list", '"event_scheduled_time"')
        self.pp.blank()

        self.pp.write_if("lib.length(future_event_list) > 0")
        self.pp.write_let("next_event", "lib.pop(future_event_list)")
        self.pp.blank()

        self.pp.comment("Advance clock")
        self.pp.write_update("sim_clocktime", "event_scheduled_time(next_event)")
        self.pp.blank()

        self.pp.comment("Store current event for dispatch")
        self.pp.write_update("current_event", "next_event")

        self.pp.write_endif()

        self.pp.write_rule_end()
        self.pp.blank()

    def _write_event_routine(self):
        """Write the event routine (dispatcher)."""
        self.pp.section_comment("Event Routine (Dispatcher)")
        self.pp.blank()

        self.pp.write_rule_start("event_routine")
        self.pp.write_let("r", "event_rule(current_event)")
        self.pp.write_let("params", "event_parameters(current_event)")
        self.pp.write_lib_call("apply_rule", "r", "params")
        self.pp.write_rule_end()
        self.pp.blank()

    def _write_run_routine(self):
        """Write the run routine."""
        self.pp.section_comment("Run Routine")
        self.pp.blank()

        self.pp.write_rule_start("run_routine")
        self.pp.write_rule_call("timing_routine")
        self.pp.write_rule_call("event_routine")
        self.pp.write_rule_end()
        self.pp.blank()

    def _write_event_rule(self, vertex: PureVertexSpec):
        """Write an event-specific rule."""
        self.pp.section_comment(f"{vertex.name} Event Rule")
        self.pp.blank()

        # Build parameter list
        params = []
        for p in vertex.parameters:
            for pname, ptype in p.items():
                params.append((pname, ptype))

        self.pp.write_rule_start(to_snake_case(vertex.name), params)

        # Translate abstract state changes to SimASM
        if vertex.state_changes:
            for op in vertex.state_changes:
                simasm_lines = self._translate_state_change(op)
                for line in simasm_lines:
                    if line.startswith("let "):
                        self.pp.line(line)
                    elif line.startswith("lib."):
                        self.pp.line(line)
                    else:
                        # It's an assignment: target := expr
                        parts = line.split(" := ", 1)
                        if len(parts) == 2:
                            self.pp.write_update(parts[0], parts[1])
                        else:
                            self.pp.line(line)
            self.pp.blank()

        # Get outgoing edges
        scheduling_edges = self.spec.get_outgoing_scheduling_edges(vertex.name)
        cancelling_edges = self.spec.get_outgoing_cancelling_edges(vertex.name)

        # Check for probabilistic branching (feedback/not_feedback pattern)
        edge_conditions = [self._translate_condition(e.condition) for e in scheduling_edges]
        if "feedback" in edge_conditions and "not_feedback" in edge_conditions:
            self.pp.comment("Probabilistic branching (feedback)")
            self.pp.write_let("feedback", "rnd.bernoulli(feedback_prob)")
            self.pp.blank()

        for i, edge in enumerate(scheduling_edges):
            self._write_edge_scheduling(edge, i)

        for edge in cancelling_edges:
            self._write_edge_cancelling(edge)

        self.pp.write_rule_end()
        self.pp.blank()

    def _write_edge_scheduling(self, edge: PureSchedulingEdgeSpec, index: int):
        """Write code to schedule an event for an edge."""
        event_type = f"{edge.target}Event"
        target_snake = to_snake_case(edge.target)
        event_var = f"{target_snake}_event" if index == 0 else f"{target_snake}_event_{index}"

        # Translate condition
        condition_str = self._translate_condition(edge.condition)

        if condition_str != "true":
            self.pp.write_if(condition_str)

        if edge.comment:
            self.pp.comment(edge.comment)
        else:
            self.pp.comment(f"Schedule {edge.target} event")

        self.pp.write_new(event_var, event_type)
        self.pp.write_update(f"event_rule({event_var})", f'"{target_snake}"')

        # Delay expression
        delay = edge.delay
        if isinstance(delay, (int, float)):
            delay_expr = "sim_clocktime" if delay == 0 else f"sim_clocktime + {delay}"
        else:
            delay_expr = f"sim_clocktime + {delay}"

        self.pp.write_update(f"event_scheduled_time({event_var})", delay_expr)

        # Parameters
        if edge.parameters:
            param_exprs = [self._translate_parameter(p) for p in edge.parameters]
            param_list = "[" + ", ".join(param_exprs) + "]"
            self.pp.write_update(f"event_parameters({event_var})", param_list)
        else:
            self.pp.write_update(f"event_parameters({event_var})", "[]")

        self.pp.write_lib_call("add", "future_event_list", event_var)

        if condition_str != "true":
            self.pp.write_endif()

        self.pp.blank()

    def _write_edge_cancelling(self, edge: PureCancellingEdgeSpec):
        """Write code to cancel events."""
        self.pp.comment(f"Cancel {edge.target} events")

        condition_str = self._translate_condition(edge.condition)
        if condition_str != "true":
            self.pp.write_if(condition_str)

        self.pp.comment("TODO: Implement event cancellation")

        if condition_str != "true":
            self.pp.write_endif()

        self.pp.blank()

    def _write_init_block(self):
        """Write the init block."""
        self.pp.block_comment("INITIAL STATE")
        self.pp.blank()

        self.pp.write_init_start()

        # Create resources
        if self.spec.resources:
            self.pp.comment("Create constant objects")
            for name, resource in self.spec.resources.items():
                self.pp.write_update(name, f"new {resource.type}")
            self.pp.blank()

        # Initialize parameters
        self.pp.comment("System parameters")
        for name, param in self.spec.parameters.items():
            self.pp.write_update(name, self.builder.format_value(param.value))
        self.pp.blank()

        # Initialize simulation state
        self.pp.comment("Time settings")
        self.pp.write_update("sim_clocktime", "0.0")
        self.pp.blank()

        # Initialize state variables
        self.pp.comment("Counters")
        for name, var in self.spec.state_variables.items():
            self.pp.write_update(name, self.builder.format_value(var.initial))

        # Initialize resource counters
        for res_name, resource in self.spec.resources.items():
            for counter_name in resource.counters:
                self.pp.write_update(f"{counter_name}({res_name})", "0")
        self.pp.blank()

        # Initialize lists
        self.pp.comment("Lists")
        self.pp.write_update("future_event_list", "[]")
        for res_name, resource in self.spec.resources.items():
            for list_name in resource.lists:
                self.pp.write_update(f"{list_name}({res_name})", "[]")
        self.pp.blank()

        # Initialize accumulators
        has_accumulators = any(r.accumulators for r in self.spec.resources.values())
        if has_accumulators:
            self.pp.comment("Time statistics")
            for res_name, resource in self.spec.resources.items():
                for acc_name in resource.accumulators:
                    self.pp.write_update(f"{acc_name}({res_name})", "0.0")

        self.pp.write_init_end()
        self.pp.blank()

    def _write_main_rule(self):
        """Write the main rule."""
        self.pp.block_comment("MAIN RULE")
        self.pp.blank()

        self.pp.write_main_rule_start()

        self.pp.comment("Initialize on first step")
        self.pp.write_if("sim_clocktime == 0.0 and lib.length(future_event_list) == 0")
        self.pp.write_rule_call("initialisation_routine")
        self.pp.write_endif()
        self.pp.blank()

        self.pp.comment("Run while events exist and time not exceeded")
        self.pp.write_if("lib.length(future_event_list) > 0 and sim_clocktime < sim_end_time")
        self.pp.write_rule_call("run_routine")
        self.pp.write_endif()

        self.pp.write_main_rule_end()
        self.pp.blank()


def convert_pure_event_graph(spec: PureEventGraphSpec) -> str:
    """Convenience function to convert a Pure Event Graph spec to SimASM."""
    converter = PureEventGraphConverter(spec)
    return converter.convert()
