"""
Activity Cycle Diagram to SimASM Converter

Converts ACD JSON specifications to SimASM source code.
Implements FINE-GRAINED step semantics for trace equivalence with Event Graph:
- One ASM step = start ONE activity OR execute ONE BTO event
- Phase-based state machine: init → scan → time → execute → scan → ...
- Activities are scanned in priority order (deterministic)

Based on:
- Activity Scanning Algorithm from Tocher (1960), Carrie (1988)
- Transformation proof: "Transformation of Activity Cycle Diagrams to ASM"
"""

from typing import List, Dict, Any, Optional
from .schema import (
    ACDSpec, ActivitySpec, QueueSpec, AtBeginSpec, AtEndArcSpec,
    TokenConsumeSpec, TokenProduceSpec, RandomStreamSpec,
    TokenTypeSpec, ObservableSpec
)
from ..codegen.pretty_printer import PrettyPrinter
from ..codegen.ast_builder import ASTBuilder


class ACDConverter:
    """
    Converts Activity Cycle Diagram specifications to SimASM code.

    The generated code implements fine-grained Activity Scanning Algorithm:

    Phase-based state machine:
    - "init": Run initialization, then → "scan"
    - "scan": Try to start ONE activity (priority order)
              If started → stay in "scan"
              If none can start → "time"
    - "time": Advance clock, pop BTO event → "execute"
    - "execute": Process BTO event (at-end actions) → "scan"
    - "done": Simulation complete

    This ensures trace equivalence with Event Graph models.
    """

    def __init__(self, spec: ACDSpec):
        self.spec = spec
        self.pp = PrettyPrinter()
        self.builder = ASTBuilder()

    def convert(self) -> str:
        """
        Convert the ACD specification to SimASM code.

        Returns the complete SimASM source code as a string.
        """
        self.pp.reset()

        # Generate each section
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
    # SECTION GENERATORS
    # =========================================================================

    def _write_header(self):
        """Write the file header."""
        self.pp.write_header(
            self.spec.model_name,
            self.spec.description,
            formalism="Activity Cycle Diagram (Fine-Grained)"
        )
        self.pp.comment("Fine-grained step semantics for trace equivalence with Event Graph")
        self.pp.comment("One ASM step = start ONE activity OR execute ONE BTO event")
        self.pp.blank()

    def _write_imports(self):
        """Write import declarations."""
        self.pp.write_imports()

    def _write_domains(self):
        """Write domain declarations."""
        self.pp.block_comment("DOMAIN DECLARATIONS")
        self.pp.blank()

        # Base domain
        self.pp.write_domain("Object")
        self.pp.blank()

        # Queue and Activity domains
        self.pp.comment("Passive states (Queues)")
        self.pp.write_domain("Queue", "Object")
        self.pp.blank()

        self.pp.comment("Active states (Activities)")
        self.pp.write_domain("Activity", "Object")
        self.pp.blank()

        # Token domains
        self.pp.comment("Tokens (entities)")
        self.pp.write_domain("Token", "Object")

        for name, token_type in self.spec.token_types.items():
            self.pp.write_domain(name, token_type.parent)

        self.pp.blank()

        # BTO Event domain
        self.pp.comment("Bound-to-occur events")
        self.pp.write_domain("BTOEvent", "Object")

        self.pp.blank()

    def _write_constants(self):
        """Write constant declarations."""
        self.pp.block_comment("QUEUE DECLARATIONS (Passive States)")
        self.pp.blank()

        for name, queue in self.spec.queues.items():
            desc = queue.description or f"{name} queue"
            self.pp.write_const(name, "Queue", desc)

        self.pp.blank()

        self.pp.block_comment("ACTIVITY DECLARATIONS (Active States)")
        self.pp.blank()

        for activity in self.spec.activities:
            desc = activity.description or f"{activity.name} activity"
            self.pp.write_const(activity.name, "Activity", desc)

        self.pp.blank()

        self.pp.block_comment("CONSTANT DECLARATIONS")
        self.pp.blank()

        for name, param in self.spec.parameters.items():
            type_str = self.builder.map_variable_type(param.type)
            self.pp.write_const(name, type_str, param.description)

        self.pp.blank()

    def _write_variables(self):
        """Write variable declarations."""
        self.pp.block_comment("DYNAMIC VARIABLE DECLARATIONS")
        self.pp.blank()

        # Core simulation variables
        self.pp.write_var("future_event_list", "List<BTOEvent>")
        self.pp.write_var("sim_clocktime", "Real")
        self.pp.write_var("current_bto_event", "BTOEvent")
        self.pp.blank()

        # Phase control for fine-grained semantics
        self.pp.comment("Phase control (fine-grained step semantics)")
        self.pp.write_var("current_phase", "String")
        self.pp.write_var("activity_started", "Bool")
        self.pp.blank()

        # Additional state variables
        if self.spec.state_variables:
            self.pp.comment("Additional state variables")
            for name, var_spec in self.spec.state_variables.items():
                if isinstance(var_spec, dict):
                    type_str = self.builder.map_variable_type(var_spec.get("type", "Nat"))
                    self.pp.write_var(name, type_str)
            self.pp.blank()

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

        self.pp.write_static_func("id", [("t", "Token")], "Nat")
        self.pp.blank()

    def _write_dynamic_functions(self):
        """Write dynamic function declarations."""
        self.pp.block_comment("DYNAMIC FUNCTION DECLARATIONS")
        self.pp.blank()

        # Marking functions (ACD state)
        self.pp.comment("Marking (token counts in queues)")
        self.pp.write_dynamic_func("marking", [("q", "Queue")], "Nat")
        self.pp.write_dynamic_func("tokens", [("q", "Queue")], "List<Token>")
        self.pp.blank()

        # BTO Event properties
        self.pp.comment("BTO-Event properties")
        self.pp.write_dynamic_func("bto_activity", [("e", "BTOEvent")], "Activity")
        self.pp.write_dynamic_func("bto_scheduled_time", [("e", "BTOEvent")], "Real")
        self.pp.write_dynamic_func("bto_tokens", [("e", "BTOEvent")], "List<Token>")
        self.pp.blank()

        # Token attributes
        for name, token_type in self.spec.token_types.items():
            if token_type.attributes:
                self.pp.comment(f"{name} attributes")
                for attr_name, attr_spec in token_type.attributes.items():
                    type_str = self.builder.map_variable_type(attr_spec.type)
                    self.pp.write_dynamic_func(attr_name, [("t", name)], type_str)
                self.pp.blank()

        self.pp.blank()

    def _write_derived_functions(self):
        """Write derived function declarations (observables)."""
        self.pp.block_comment("OBSERVABLE STATE (Derived Functions)")
        self.pp.blank()

        # Standard observables aligned with Event Graph
        for name, obs in self.spec.observables.items():
            # Determine return type
            return_type = "Nat" if any(x in name.lower() for x in ["count", "busy", "system"]) else "Bool"
            self.pp.write_derived_func(obs.name, [], return_type, obs.expression)
            self.pp.blank()

        # At-begin conditions for each activity
        self.pp.comment("At-begin conditions (activity enabling)")
        for activity in self.spec.get_activities_by_priority():
            condition = self.spec.get_enabling_condition(activity.name)
            self.pp.write_derived_func(
                f"at_begin_condition_{activity.name.lower()}",
                [],
                "Bool",
                condition
            )
        self.pp.blank()

    def _write_rules(self):
        """Write all rules."""
        self.pp.block_comment("RULES (ACD Phases)")
        self.pp.blank()

        # Initialization routine
        self._write_initialization_routine()

        # At-begin action rules for each activity
        for activity in self.spec.activities:
            self._write_at_begin_rule(activity)

        # At-end action rules for each activity
        for activity in self.spec.activities:
            self._write_at_end_rule(activity)

        # Scanning phase (fine-grained: try ONE activity)
        self._write_scanning_phase_single()

        # Timing phase
        self._write_timing_phase()

        # Executing phase
        self._write_executing_phase()

    def _write_initialization_routine(self):
        """Write the initialization routine."""
        self.pp.section_comment("Phase 0: Initialization")
        self.pp.blank()

        self.pp.write_rule_start("initialisation_routine")

        # Initialize tokens in each queue
        for queue_name, queue in self.spec.queues.items():
            if queue.initial_tokens > 0:
                self.pp.comment(f"Initialize {queue_name} with {queue.initial_tokens} tokens")
                self.pp.write_update(f"tokens({queue_name})", "[]")
                # Create tokens
                for i in range(queue.initial_tokens):
                    token_type = queue.token_type
                    self.pp.write_let(f"token_{i}", f"new {token_type}")
                    self.pp.write_update(f"id(token_{i})", str(i + 1))
                    self.pp.write_lib_call("add", f"tokens({queue_name})", f"token_{i}")
                self.pp.blank()

        self.pp.write_rule_end()
        self.pp.blank()

    def _write_at_begin_rule(self, activity: ActivitySpec):
        """Write at-begin action rule for an activity."""
        self.pp.section_comment(f"At-begin: {activity.name}")
        self.pp.blank()

        self.pp.write_rule_start(f"at_begin_action_{activity.name.lower()}")

        # Consume tokens from input queues
        bound_tokens = []
        for consume in activity.at_begin.consume:
            self.pp.comment(f"Consume from {consume.queue}")
            self.pp.write_update(f"marking({consume.queue})",
                               f"marking({consume.queue}) - {consume.count}")
            if consume.bind_as:
                self.pp.write_let(consume.bind_as, f"lib.pop(tokens({consume.queue}))")
                bound_tokens.append(consume.bind_as)
            else:
                self.pp.write_lib_call("pop", f"tokens({consume.queue})")
        self.pp.blank()

        # Additional at-begin actions
        for action in activity.at_begin.actions:
            if ":=" in action:
                parts = action.split(":=")
                self.pp.write_update(parts[0].strip(), parts[1].strip())
            else:
                self.pp.line(action)

        # Schedule BTO event
        self.pp.comment("Schedule BTO-event")
        self.pp.write_new("bto_event", "BTOEvent")
        self.pp.write_update("bto_activity(bto_event)", activity.name)

        # Duration
        duration = activity.duration
        if isinstance(duration, (int, float)):
            self.pp.write_update("bto_scheduled_time(bto_event)",
                               f"sim_clocktime + {duration}")
        else:
            self.pp.write_update("bto_scheduled_time(bto_event)",
                               f"sim_clocktime + {duration}")

        # Bound tokens
        if bound_tokens:
            tokens_list = "[" + ", ".join(bound_tokens) + "]"
            self.pp.write_update("bto_tokens(bto_event)", tokens_list)
        else:
            self.pp.write_update("bto_tokens(bto_event)", "[]")

        self.pp.write_lib_call("add", "future_event_list", "bto_event")

        self.pp.write_rule_end()
        self.pp.blank()

    def _write_at_end_rule(self, activity: ActivitySpec):
        """Write at-end action rule for an activity."""
        self.pp.section_comment(f"At-end: {activity.name}")
        self.pp.blank()

        self.pp.write_rule_start(f"at_end_action_{activity.name.lower()}",
                                [("bound_tokens", "List<Token>")])

        # Build map from binding name to index in bound_tokens
        binding_to_idx = {}
        for idx, consume in enumerate(activity.at_begin.consume):
            if consume.bind_as:
                binding_to_idx[consume.bind_as] = idx

        # Check for probabilistic branching (feedback/not_feedback pattern)
        arc_conditions = [arc.condition for arc in activity.at_end]
        has_feedback = ("feedback" in arc_conditions and
                       "not_feedback" in arc_conditions)
        if has_feedback:
            self.pp.comment("Probabilistic branching (feedback)")
            self.pp.write_let("feedback", "rnd.bernoulli(feedback_prob)")
            self.pp.blank()

        # Track new token counter for this rule
        new_token_counter = 0

        # Process each at-end arc
        for arc_idx, arc in enumerate(activity.at_end):
            # Translate probabilistic conditions
            condition = arc.condition
            if has_feedback:
                if condition == "feedback":
                    condition = "feedback"
                elif condition == "not_feedback":
                    condition = "not feedback"

            if condition != "true":
                self.pp.write_if(condition)

            # Produce tokens to output queues
            for prod_idx, produce in enumerate(arc.produce):
                self.pp.comment(f"Produce to {produce.queue}")

                if produce.token_source == "new":
                    # Create new token
                    token_type = self.spec.queues[produce.queue].token_type
                    var_name = f"new_token_{new_token_counter}"
                    self.pp.write_let(var_name, f"new {token_type}")
                    self.pp.write_lib_call("add", f"tokens({produce.queue})", var_name)
                    new_token_counter += 1
                elif produce.token_source:
                    # Release bound token - look up by binding name
                    binding_name = produce.token_source
                    if binding_name in binding_to_idx:
                        idx = binding_to_idx[binding_name]
                        self.pp.write_let(binding_name,
                                         f"lib.get(bound_tokens, {idx})")
                        self.pp.write_lib_call("add", f"tokens({produce.queue})",
                                              binding_name)
                    else:
                        # Fallback: use prod_idx
                        self.pp.write_let(f"token_{prod_idx}",
                                         f"lib.get(bound_tokens, {prod_idx})")
                        self.pp.write_lib_call("add", f"tokens({produce.queue})",
                                              f"token_{prod_idx}")
                else:
                    # Generic release
                    self.pp.write_let(f"token_{prod_idx}",
                                     f"lib.get(bound_tokens, {prod_idx})")
                    self.pp.write_lib_call("add", f"tokens({produce.queue})",
                                          f"token_{prod_idx}")

                self.pp.write_update(f"marking({produce.queue})",
                                   f"marking({produce.queue}) + {produce.count}")

            # Additional at-end actions
            for action in arc.actions:
                if ":=" in action:
                    parts = action.split(":=")
                    self.pp.write_update(parts[0].strip(), parts[1].strip())
                else:
                    self.pp.line(action)

            if condition != "true":
                self.pp.write_endif()

        self.pp.write_rule_end()
        self.pp.blank()

    def _write_scanning_phase_single(self):
        """Write scanning phase that starts AT MOST ONE activity."""
        self.pp.section_comment("Phase 1: Scanning Phase (Fine-Grained - ONE activity)")
        self.pp.blank()

        self.pp.write_rule_start("scanning_phase_single")

        self.pp.write_update("activity_started", "false")
        self.pp.blank()

        # Try activities in priority order
        sorted_activities = self.spec.get_activities_by_priority()

        for i, activity in enumerate(sorted_activities):
            condition = f"at_begin_condition_{activity.name.lower()}()"

            if i == 0:
                self.pp.comment(f"Try {activity.name} (priority {activity.priority})")
                self.pp.write_if(f"not activity_started and {condition}")
            else:
                self.pp.blank()
                self.pp.comment(f"Try {activity.name} (priority {activity.priority})")
                self.pp.write_if(f"not activity_started and {condition}")

            self.pp.write_rule_call(f"at_begin_action_{activity.name.lower()}")
            self.pp.write_update("activity_started", "true")
            self.pp.write_endif()

        self.pp.write_rule_end()
        self.pp.blank()

    def _write_timing_phase(self):
        """Write timing phase."""
        self.pp.section_comment("Phase 2: Timing Phase")
        self.pp.blank()

        self.pp.write_rule_start("timing_phase")

        # Sort FEL
        self.pp.comment("Sort FEL by scheduled time")
        self.pp.write_lib_call("sort", "future_event_list", '"bto_scheduled_time"')
        self.pp.blank()

        # Get next event
        self.pp.write_let("next_event", "lib.pop(future_event_list)")
        self.pp.blank()

        # Advance clock
        self.pp.comment("Advance clock")
        self.pp.write_update("sim_clocktime", "bto_scheduled_time(next_event)")
        self.pp.blank()

        # Execute at-end
        self.pp.comment("Execute at-end actions")
        self.pp.write_rule_call("executing_phase", "next_event")

        self.pp.write_rule_end()
        self.pp.blank()

    def _write_executing_phase(self):
        """Write executing phase."""
        self.pp.section_comment("Phase 3: Executing Phase")
        self.pp.blank()

        self.pp.write_rule_start("executing_phase", [("bto_event", "BTOEvent")])

        self.pp.write_let("activity", "bto_activity(bto_event)")
        self.pp.write_let("bound_tokens", "bto_tokens(bto_event)")
        self.pp.blank()

        # Dispatch to appropriate at-end rule
        for i, activity in enumerate(self.spec.activities):
            if i == 0:
                self.pp.write_if(f"activity == {activity.name}")
            else:
                self.pp.write_endif()
                self.pp.blank()
                self.pp.write_if(f"activity == {activity.name}")

            self.pp.write_rule_call(f"at_end_action_{activity.name.lower()}",
                                   "bound_tokens")

        self.pp.write_endif()

        self.pp.write_rule_end()
        self.pp.blank()

    def _write_init_block(self):
        """Write the init block."""
        self.pp.block_comment("INITIAL STATE")
        self.pp.blank()

        self.pp.write_init_start()

        # Create queue objects
        self.pp.comment("Create queue objects")
        for name in self.spec.queues.keys():
            self.pp.write_update(name, "new Queue")
        self.pp.blank()

        # Create activity objects
        self.pp.comment("Create activity objects")
        for activity in self.spec.activities:
            self.pp.write_update(activity.name, "new Activity")
        self.pp.blank()

        # Initialize parameters
        self.pp.comment("Parameters")
        for name, param in self.spec.parameters.items():
            self.pp.write_update(name, self.builder.format_value(param.value))
        self.pp.blank()

        # Initialize markings
        self.pp.comment("Initial markings")
        for name, queue in self.spec.queues.items():
            self.pp.write_update(f"marking({name})", str(queue.initial_tokens))
        self.pp.blank()

        # Initialize token lists (empty - will be populated by init routine)
        self.pp.comment("Initialize token lists")
        for name in self.spec.queues.keys():
            self.pp.write_update(f"tokens({name})", "[]")
        self.pp.blank()

        # Simulation state
        self.pp.comment("Simulation state")
        self.pp.write_update("sim_clocktime", "0.0")
        self.pp.write_update("future_event_list", "[]")
        self.pp.blank()

        # Phase control
        self.pp.comment("Phase control (fine-grained)")
        self.pp.write_update("current_phase", '"init"')
        self.pp.write_update("activity_started", "false")
        self.pp.blank()

        # Additional state variables
        if self.spec.state_variables:
            self.pp.comment("Additional state variables")
            for name, var_spec in self.spec.state_variables.items():
                if isinstance(var_spec, dict):
                    initial = var_spec.get("initial", 0)
                    self.pp.write_update(name, self.builder.format_value(initial))
            self.pp.blank()

        self.pp.write_init_end()
        self.pp.blank()

    def _write_main_rule(self):
        """Write the main rule with fine-grained phase control."""
        self.pp.block_comment("MAIN RULE (Fine-Grained Activity Scanning)")
        self.pp.blank()

        self.pp.write_main_rule_start()

        # Phase: init
        self.pp.comment("Phase: init - Initialize and switch to scan")
        self.pp.write_if('current_phase == "init"')
        self.pp.write_rule_call("initialisation_routine")
        self.pp.write_update("current_phase", '"scan"')
        self.pp.write_endif()
        self.pp.blank()

        # Check stopping condition
        self.pp.comment("Run while not stopped")
        self.pp.write_if("sim_clocktime < sim_end_time")

        # Phase: scan
        self.pp.write_if('current_phase == "scan"')
        self.pp.write_rule_call("scanning_phase_single")
        self.pp.comment("If no activity started, switch to timing")
        self.pp.write_if("not activity_started")
        self.pp.write_update("current_phase", '"time"')
        self.pp.write_endif()
        self.pp.comment("If activity started, stay in scan to try more")

        # Phase: time
        self.pp.write_else()
        self.pp.comment("current_phase == \"time\"")
        self.pp.write_if("lib.length(future_event_list) > 0")
        self.pp.write_rule_call("timing_phase")
        self.pp.write_endif()
        self.pp.write_update("current_phase", '"scan"')
        self.pp.write_endif()

        self.pp.write_endif()

        self.pp.write_main_rule_end()
        self.pp.blank()


def convert_acd(spec: ACDSpec) -> str:
    """
    Convenience function to convert an ACD spec to SimASM.

    Args:
        spec: The ACD specification

    Returns:
        SimASM source code as a string
    """
    converter = ACDConverter(spec)
    return converter.convert()
