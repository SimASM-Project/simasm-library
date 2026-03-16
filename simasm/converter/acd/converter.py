"""
Activity Cycle Diagram to SimASM Converter

Converts ACD specifications in Activity Transition Table JSON format to SimASM code.
Based on the Activity Scanning Algorithm from ByongKyu (2013).

The converter generates SimASM code that implements:
- Fine-grained phase-based state machine: init → scan → time → execute → scan → ...
- One activity start OR one BTO execution per ASM step
- Deterministic scanning order based on activity priorities
"""

import re
from typing import List, Dict, Optional, Set, Tuple
from io import StringIO

from .schema import (
    ACDSpec, ActivitySpec, AtBeginSpec, BTOEventSpec, AtEndArcSpec,
    QueueSpec, TokenTypeSpec, ParameterSpec, RandomStreamSpec,
    ObservableSpec, StateVariableSpec,
    load_acd_from_json
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


class ACDConverter:
    """
    Converts ACD v2 specification to SimASM code.

    Generates code structure:
    1. Header and imports
    2. Domain declarations
    3. Queue and Activity constants
    4. Parameters
    5. State variables and random streams
    6. Dynamic functions (marking, tokens, BTO properties)
    7. Observables (derived functions)
    8. At-begin condition functions
    9. Rules (initialization, at-begin actions, at-end actions)
    10. Phase rules (scanning, timing, executing)
    11. Init block
    12. Main rule
    """

    def __init__(self, spec: ACDSpec):
        self.spec = spec
        self.pp = SimASMPrettyPrinter()

        # Derive defaults from schema
        self._derive_defaults()

    def _derive_defaults(self):
        """
        Derive default behavior from schema conventions.

        Backend conventions:
        1. Statistics: Auto-generate time_average for each observable
        2. State variables: Auto-generate accumulators (total_sojourn_time, etc.)
        3. Token timestamps: Auto-set service_start_time when Job leaves queue
        4. Departure counting: Auto-increment departure_count at sink queue
        """
        # 1. Auto-generate statistics from observables if not specified
        if not self.spec.statistics:
            from .schema import StatisticSpec
            self.spec.statistics = []
            for name, obs in self.spec.observables.items():
                stat_name = f"L_{name}" if not name.startswith("L_") else name
                self.spec.statistics.append(StatisticSpec(
                    name=stat_name,
                    type="time_average",
                    observable=name,
                    description=f"Time average of {name}"
                ))

        # 2. Auto-generate standard state variables if not specified
        from .schema import StateVariableSpec
        default_state_vars = {
            "job_id_counter": StateVariableSpec(type="Nat", initial=0),
            "departure_count": StateVariableSpec(type="Nat", initial=0),
            "total_sojourn_time": StateVariableSpec(type="Real", initial=0.0),
            "total_time_in_queue": StateVariableSpec(type="Real", initial=0.0),
        }
        for name, sv in default_state_vars.items():
            if name not in self.spec.state_variables:
                self.spec.state_variables[name] = sv

        # 3. Find sink queue (for auto-departure counting)
        self.sink_queue = None
        for name, queue in self.spec.queues.items():
            # Convention: queue named "Jobs" or marked is_sink is the sink
            if name == "Jobs" or getattr(queue, 'is_sink', False):
                self.sink_queue = name
                break

        # 4. Find Job token type for auto-timestamping
        self.job_token_type = None
        for name, tt in self.spec.token_types.items():
            if name == "Job" or "arrival_time" in tt.attributes:
                self.job_token_type = name
                break

    def convert(self) -> str:
        """Convert the ACD spec to SimASM code."""
        self._write_header()
        self._write_imports()
        self._write_domains()
        self._write_queue_declarations()
        self._write_activity_declarations()
        self._write_parameters()
        self._write_state_variables()
        self._write_random_streams()
        self._write_dynamic_functions()
        self._write_observables()
        self._write_at_begin_conditions()
        self._write_rules()
        self._write_init_block()
        self._write_main_rule()

        return self.pp.get_output()

    def _write_header(self):
        """Write file header."""
        self.pp.section_comment(
            f"Activity Cycle Diagram M/M/n Queue - SimASM v1.0"
        )
        if self.spec.description:
            for line in self.spec.description.split('\n'):
                self.pp.comment(line)
        self.pp.comment("Based on Tocher (1960), Carrie (1988)")
        self.pp.comment("Three-phase approach: A-phase (time advance), B-phase (scan), C-phase (execute)")
        self.pp.section_comment("")
        self.pp.blank()

    def _write_imports(self):
        """Write import statements."""
        self.pp.section_comment("IMPORT LIBRARIES")
        self.pp.blank()
        self.pp.writeln("import Random as rnd")
        self.pp.writeln("import Stdlib as lib")
        self.pp.blank()

    def _write_domains(self):
        """Write domain declarations."""
        self.pp.section_comment("DOMAIN DECLARATIONS")
        self.pp.blank()
        self.pp.writeln("domain Object")
        self.pp.blank()
        self.pp.comment("Passive states (Queues - ovals in ACD)")
        self.pp.writeln("domain Queue <: Object")
        self.pp.blank()
        self.pp.comment("Active states (Activities - rectangles in ACD)")
        self.pp.writeln("domain Activity")
        self.pp.blank()
        self.pp.comment("Tokens (entities flowing through the diagram)")
        self.pp.writeln("domain Token <: Object")

        # Write custom token types
        for name, tt in self.spec.token_types.items():
            parent = tt.parent if tt.parent else "Token"
            self.pp.writeln(f"domain {name} <: {parent}")

        self.pp.blank()
        self.pp.comment("Bound-to-occur events")
        self.pp.writeln("domain BTOEvent")
        self.pp.blank()

    def _write_queue_declarations(self):
        """Write queue constant declarations."""
        self.pp.section_comment("QUEUE DECLARATIONS (Passive States)")
        self.pp.blank()
        for name, queue in self.spec.queues.items():
            desc = f"  // {queue.description}" if queue.description else ""
            self.pp.writeln(f"const {name}: Queue{desc}")
        self.pp.blank()

    def _write_activity_declarations(self):
        """Write activity constant declarations."""
        self.pp.section_comment("ACTIVITY DECLARATIONS (Active States)")
        self.pp.blank()
        for activity in self.spec.activities:
            desc = f"  // {activity.description}" if activity.description else ""
            self.pp.writeln(f"const {activity.name}: Activity{desc}")
        self.pp.blank()

    def _write_parameters(self):
        """Write parameter declarations."""
        self.pp.section_comment("CONSTANT DECLARATIONS")
        self.pp.blank()
        for name, param in self.spec.parameters.items():
            desc = f"  // {param.description}" if param.description else ""
            self.pp.writeln(f"const {name}: {param.type}{desc}")
        self.pp.blank()

    def _write_state_variables(self):
        """Write state variable declarations."""
        self.pp.section_comment("DYNAMIC VARIABLE DECLARATIONS")
        self.pp.blank()
        self.pp.writeln("var future_event_list: List<BTOEvent>")
        self.pp.writeln("var sim_clocktime: Real")
        self.pp.writeln("var activities_started: Bool")
        self.pp.writeln("var current_phase: String")

        for name, sv in self.spec.state_variables.items():
            self.pp.writeln(f"var {name}: {sv.type}")

        self.pp.blank()

    def _write_random_streams(self):
        """Write random stream declarations."""
        self.pp.section_comment("RANDOM STREAM VARIABLES")
        self.pp.blank()
        for name, rs in self.spec.random_streams.items():
            dist = rs.distribution
            params = rs.params

            # Build parameter string
            if dist == "exponential":
                param_str = params.get("mean", "1.0")
            elif dist == "uniform":
                param_str = f"{params.get('min', 0)}, {params.get('max', 1)}"
            elif dist == "normal":
                param_str = f"{params.get('mean', 0)}, {params.get('std', 1)}"
            else:
                param_str = ", ".join(str(v) for v in params.values())

            stream = f' as "{rs.stream_name}"' if rs.stream_name else ""
            self.pp.writeln(f"var {name}: rnd.{dist}({param_str}){stream}")

        self.pp.blank()

    def _write_dynamic_functions(self):
        """Write dynamic function declarations."""
        self.pp.section_comment("DYNAMIC FUNCTION DECLARATIONS")
        self.pp.blank()

        self.pp.comment("Marking (token counts in queues)")
        self.pp.writeln("dynamic function marking(q: Queue): Nat")
        self.pp.writeln("dynamic function tokens(q: Queue): List<Token>")
        self.pp.blank()

        self.pp.comment("BTO-Event properties")
        self.pp.writeln("dynamic function bto_activity(e: BTOEvent): Activity")
        self.pp.writeln("dynamic function bto_scheduled_time(e: BTOEvent): Real")
        self.pp.writeln("dynamic function bto_tokens(e: BTOEvent): List<Token>")
        self.pp.blank()

        # Write token attribute functions
        self.pp.comment("statistics collector")
        for tt_name, tt in self.spec.token_types.items():
            for attr_name, attr_type in tt.attributes.items():
                self.pp.writeln(f"dynamic function {attr_name}(j: {tt_name}): {attr_type}")

        self.pp.blank()
        self.pp.comment("Token identification")
        self.pp.writeln("static function id(t: Token): Nat")
        self.pp.blank()

    def _write_observables(self):
        """Write observable derived functions."""
        self.pp.subsection_comment("Observable State (aligned with Event Graph)")
        self.pp.blank()

        for name, obs in self.spec.observables.items():
            ret_type = obs.return_type if obs.return_type else "Nat"
            self.pp.writeln(f"derived function {name}(): {ret_type} =")
            self.pp.indent()
            self.pp.writeln(obs.expression)
            self.pp.dedent()
            self.pp.blank()

    def _write_at_begin_conditions(self):
        """Write at-begin condition derived functions."""
        self.pp.section_comment("AT-BEGIN CONDITIONS (Activity start preconditions)")
        self.pp.blank()

        for activity in self.spec.activities:
            func_name = f"at_begin_condition_{activity.name.lower()}"
            condition = activity.at_begin.condition

            # Convert >= to > for marking checks (standard ACD uses > 0)
            # Actually keep as-is since it matches the table format

            self.pp.writeln(f"derived function {func_name}(): Bool =")
            self.pp.indent()
            self.pp.writeln(condition)
            self.pp.dedent()
            self.pp.blank()

    def _write_rules(self):
        """Write all rules."""
        self.pp.section_comment("RULES (ACD Phases)")
        self.pp.blank()

        self._write_init_routine()
        self._write_at_begin_actions()
        self._write_at_end_actions()
        self._write_scanning_phase()
        self._write_timing_phase()
        self._write_executing_phase()

    def _write_init_routine(self):
        """Write initialization routine."""
        self.pp.subsection_comment("Phase 0: Initialization")
        self.pp.blank()

        self.pp.writeln("rule initialisation_routine() =")
        self.pp.indent()

        # Identify creator queues (name starts with C, is_resource = true)
        # and server queues (name starts with S, is_resource = true)
        creator_queues = []
        server_queues = []

        for name, queue in self.spec.queues.items():
            if queue.is_resource:
                initial = queue.initial_marking
                # Creator queues typically start with C and have initial_marking = 1
                if name.startswith("C") and isinstance(initial, int) and initial == 1:
                    creator_queues.append(name)
                # Server queues typically start with S
                elif name.startswith("S"):
                    server_queues.append((name, initial))

        # Initialize creator tokens
        creator_id = 0
        for name in creator_queues:
            creator_id += 1
            self.pp.comment(f"Initialize {name} creator token")
            self.pp.writeln(f"let creator_{name.lower()} = new Resource")
            self.pp.writeln(f"id(creator_{name.lower()}) := {creator_id}")
            self.pp.writeln(f"tokens({name}) := [creator_{name.lower()}]")
            self.pp.blank()

        # Initialize server tokens
        for name, capacity in server_queues:
            self.pp.comment(f"Initialize {name} server tokens")
            self.pp.writeln(f"tokens({name}) := []")
            self.pp.writeln(f"init_servers_{name.lower()}({capacity})")
            self.pp.blank()

        self.pp.dedent()
        self.pp.writeln("endrule")
        self.pp.blank()

        # Generate helper rules for each server queue
        for name, capacity in server_queues:
            # Determine capacity param name for ID offset
            if isinstance(capacity, str):
                capacity_param = capacity
            else:
                capacity_param = str(capacity)

            self.pp.comment(f"Helper rule to initialize {name} server tokens")
            self.pp.writeln(f"rule init_servers_{name.lower()}(remaining: Nat) =")
            self.pp.indent()
            self.pp.writeln("if remaining > 0 then")
            self.pp.indent()
            self.pp.writeln("let server_token = new Resource")
            # Use offset based on queue name to avoid ID collisions
            offset = (ord(name[-1]) - ord('0')) * 100 if name[-1].isdigit() else 0
            self.pp.writeln(f"id(server_token) := {offset} + ({capacity_param} - remaining + 1)")
            self.pp.writeln(f"lib.add(tokens({name}), server_token)")
            self.pp.writeln(f"init_servers_{name.lower()}(remaining - 1)")
            self.pp.dedent()
            self.pp.writeln("endif")
            self.pp.dedent()
            self.pp.writeln("endrule")
            self.pp.blank()

    def _write_at_begin_actions(self):
        """Write at-begin action rules."""
        self.pp.subsection_comment("At-begin Actions (Activity instantiation)")
        self.pp.blank()

        for activity in self.spec.activities:
            self._write_at_begin_action(activity)

    def _write_at_begin_action(self, activity: ActivitySpec):
        """Write at-begin action rule for one activity."""
        name_lower = activity.name.lower()
        self.pp.writeln(f"rule at_begin_action_{name_lower}() =")
        self.pp.indent()

        # Parse bindings from at_begin.bind
        bindings = self._parse_bindings(activity.at_begin.bind)

        # Generate consume code for each binding
        for var_name, queue_name in bindings:
            self.pp.comment(f"Consume {var_name} from {queue_name}")
            self.pp.writeln(f"marking({queue_name}) := marking({queue_name}) - 1")
            self.pp.writeln(f"let {var_name} = lib.pop(tokens({queue_name}))")

            # Convention: Auto-set service_start_time when Job token leaves waiting queue
            # (i.e., when it's not a resource queue and the token type has service_start_time)
            queue_spec = self.spec.queues.get(queue_name)
            if queue_spec and not queue_spec.is_resource:
                token_type = queue_spec.token_type
                token_spec = self.spec.token_types.get(token_type)
                if token_spec and "service_start_time" in token_spec.attributes:
                    self.pp.writeln(f"service_start_time({var_name}) := sim_clocktime")

            self.pp.blank()

        # Process at_begin.set assignments (explicit overrides)
        for set_expr in activity.at_begin.set:
            # Parse "job_token.service_start_time = sim_clocktime"
            simasm_expr = self._translate_set_expr(set_expr)
            self.pp.writeln(simasm_expr)

        self.pp.blank()

        # Schedule BTO event
        self.pp.comment("Schedule BTO-event for activity completion")
        self.pp.writeln("let bto_event = new BTOEvent")
        self.pp.writeln(f"bto_activity(bto_event) := {activity.name}")
        duration_var = activity.bto_event.time
        self.pp.writeln(f"bto_scheduled_time(bto_event) := sim_clocktime + {duration_var}")

        # Store bound tokens
        token_list = ", ".join(var_name for var_name, _ in bindings)
        self.pp.writeln(f"bto_tokens(bto_event) := [{token_list}]")
        self.pp.writeln("lib.add(future_event_list, bto_event)")

        self.pp.dedent()
        self.pp.writeln("endrule")
        self.pp.blank()

    def _write_at_end_actions(self):
        """Write at-end action rules."""
        self.pp.subsection_comment("At-end Actions (Activity completion)")
        self.pp.blank()

        for activity in self.spec.activities:
            self._write_at_end_action(activity)

    def _write_at_end_action(self, activity: ActivitySpec):
        """Write at-end action rule for one activity."""
        name_lower = activity.name.lower()
        self.pp.writeln(f"rule at_end_action_{name_lower}(bound_tokens: List<Token>) =")
        self.pp.indent()

        # Get bindings to know token order
        bindings = self._parse_bindings(activity.at_begin.bind)

        for arc in activity.at_end:
            self.pp.comment(f"Arc {arc.arc}: {arc.action}")

            # Check if arc has a condition (for blocking queues)
            has_condition = arc.condition and arc.condition.lower() != "true"

            if has_condition:
                self.pp.writeln(f"if {arc.condition} then")
                self.pp.indent()

            # Parse the action string and detect sink queue destinations
            actions, sink_job_var = self._parse_arc_action_with_sink_detection(arc.action, bindings)

            for action in actions:
                self.pp.writeln(action)

            # Handle explicit compute expressions
            for compute_expr in arc.compute:
                simasm = self._translate_compute(compute_expr)
                self.pp.writeln(simasm)

            # Handle explicit accumulate expressions
            for acc_expr in arc.accumulate:
                simasm = self._translate_accumulate(acc_expr)
                self.pp.writeln(simasm)

            # Convention: Auto-generate departure statistics when Job goes to sink queue
            if sink_job_var and not arc.compute and not arc.accumulate:
                self.pp.writeln(f"let time_in_system = sim_clocktime - arrival_time({sink_job_var})")
                self.pp.writeln(f"total_sojourn_time := total_sojourn_time + time_in_system")
                # Only compute time_in_queue if Job token type has service_start_time attribute
                job_spec = self.spec.token_types.get(self.job_token_type) if self.job_token_type else None
                if job_spec and "service_start_time" in job_spec.attributes:
                    self.pp.writeln(f"let time_in_queue = service_start_time({sink_job_var}) - arrival_time({sink_job_var})")
                    self.pp.writeln(f"total_time_in_queue := total_time_in_queue + time_in_queue")
                self.pp.writeln(f"departure_count := departure_count + 1")

            if has_condition:
                self.pp.dedent()
                self.pp.writeln("endif")

            self.pp.blank()

        self.pp.dedent()
        self.pp.writeln("endrule")
        self.pp.blank()

    def _write_scanning_phase(self):
        """Write scanning phase rule."""
        self.pp.subsection_comment("Phase 1: B-phase (Scanning Phase) - One activity per step")
        self.pp.blank()

        self.pp.writeln("rule scanning_phase_single() =")
        self.pp.indent()
        self.pp.writeln("activities_started := false")
        self.pp.blank()

        # Scan activities in priority order
        activities = self.spec.get_activities_by_priority()
        for i, activity in enumerate(activities):
            name_lower = activity.name.lower()
            comment = "first" if i == 0 else f"only if previous didn't start"
            self.pp.comment(f"Try {activity.name} {comment}")
            self.pp.writeln(f"if not activities_started and at_begin_condition_{name_lower}() then")
            self.pp.indent()
            self.pp.writeln(f"at_begin_action_{name_lower}()")
            self.pp.writeln("activities_started := true")
            self.pp.dedent()
            self.pp.writeln("endif")
            self.pp.blank()

        self.pp.dedent()
        self.pp.writeln("endrule")
        self.pp.blank()

    def _write_timing_phase(self):
        """Write timing phase rule."""
        self.pp.subsection_comment("Phase 2: A-phase (Timing Phase) - advance clock")
        self.pp.blank()

        self.pp.writeln("rule timing_phase() =")
        self.pp.indent()
        self.pp.comment("Sort FEL by scheduled time (uses dynamic function lookup)")
        self.pp.writeln('lib.sort(future_event_list, "bto_scheduled_time")')
        self.pp.blank()
        self.pp.comment("Get next event")
        self.pp.writeln("let next_event = lib.pop(future_event_list)")
        self.pp.blank()
        self.pp.comment("Advance clock")
        self.pp.writeln("sim_clocktime := bto_scheduled_time(next_event)")
        self.pp.blank()
        self.pp.comment("Execute the event")
        self.pp.writeln("executing_phase(next_event)")
        self.pp.dedent()
        self.pp.writeln("endrule")
        self.pp.blank()

    def _write_executing_phase(self):
        """Write executing phase rule."""
        self.pp.subsection_comment("Phase 3: C-phase (Executing Phase)")
        self.pp.blank()

        self.pp.writeln("rule executing_phase(bto_event: BTOEvent) =")
        self.pp.indent()
        self.pp.writeln("let activity = bto_activity(bto_event)")
        self.pp.writeln("let bound_tokens = bto_tokens(bto_event)")
        self.pp.blank()

        for activity in self.spec.activities:
            name_lower = activity.name.lower()
            self.pp.writeln(f"if activity == {activity.name} then")
            self.pp.indent()
            self.pp.writeln(f"at_end_action_{name_lower}(bound_tokens)")
            self.pp.dedent()
            self.pp.writeln("endif")
            self.pp.blank()

        self.pp.dedent()
        self.pp.writeln("endrule")
        self.pp.blank()

        self.pp.subsection_comment("Run Routine (removed - phases now controlled by main rule)")
        self.pp.blank()

    def _write_init_block(self):
        """Write init block."""
        self.pp.section_comment("INITIAL STATE")
        self.pp.blank()

        self.pp.writeln("init:")
        self.pp.indent()

        # Create queue objects
        self.pp.comment("Create constant objects (Queues and Activities)")
        for name in self.spec.queues.keys():
            self.pp.writeln(f"{name} := new Queue")
        for activity in self.spec.activities:
            self.pp.writeln(f"{activity.name} := new Activity")
        self.pp.blank()

        # Set parameters
        self.pp.comment("M/M/n configuration (must be set before markings that depend on it)")
        for name, param in self.spec.parameters.items():
            self.pp.writeln(f"{name} := {param.value}")
        self.pp.blank()

        # Initialize markings
        self.pp.comment("Initialize markings (matching EG initial state: 0 busy, 0 in queue)")
        for name, queue in self.spec.queues.items():
            initial = queue.initial_marking
            # Handle special case where initial_marking references a parameter
            if isinstance(initial, str):
                self.pp.writeln(f"marking({name}) := {initial}")
            else:
                self.pp.writeln(f"marking({name}) := {initial}")
        self.pp.blank()

        # Initialize token lists
        self.pp.comment("Initialize token lists")
        for name in self.spec.queues.keys():
            self.pp.writeln(f"tokens({name}) := []")
        self.pp.blank()

        # Simulation variables
        self.pp.comment("Simulation bounds")
        self.pp.writeln("sim_clocktime := 0.0")

        # State variables
        for name, sv in self.spec.state_variables.items():
            self.pp.writeln(f"{name} := {sv.initial}")
        self.pp.blank()

        # FEL
        self.pp.comment("Initialize FEL")
        self.pp.writeln("future_event_list := []")
        self.pp.blank()

        # Phase control
        self.pp.comment("Scanning flag and phase control")
        self.pp.writeln("activities_started := false")
        self.pp.writeln('current_phase := "scan"')

        self.pp.dedent()
        self.pp.writeln("endinit")
        self.pp.blank()

    def _write_main_rule(self):
        """Write main rule."""
        self.pp.section_comment("MAIN RULE")
        self.pp.blank()

        self.pp.writeln("main rule main =")
        self.pp.indent()

        # Find first creator queue for initialization check
        first_creator = None
        for name, queue in self.spec.queues.items():
            if queue.is_resource and name.startswith("C"):
                initial = queue.initial_marking
                if isinstance(initial, int) and initial == 1:
                    first_creator = name
                    break

        if not first_creator:
            first_creator = "C"  # Fallback

        self.pp.comment(f"Initialize tokens on first step (tokens({first_creator}) is empty until initialisation_routine runs)")
        self.pp.writeln(f"if sim_clocktime == 0.0 and lib.length(tokens({first_creator})) == 0 then")
        self.pp.indent()
        self.pp.writeln("initialisation_routine()")
        self.pp.writeln('current_phase := "scan"')
        self.pp.dedent()
        self.pp.writeln("endif")
        self.pp.blank()

        self.pp.comment("Run while time not exceeded")
        self.pp.writeln("if sim_clocktime < sim_end_time then")
        self.pp.indent()
        self.pp.writeln('if current_phase == "scan" then')
        self.pp.indent()
        self.pp.writeln("scanning_phase_single()")
        self.pp.comment("Switch to timing only if no activity could start")
        self.pp.writeln("if not activities_started then")
        self.pp.indent()
        self.pp.writeln('current_phase := "time"')
        self.pp.dedent()
        self.pp.writeln("endif")
        self.pp.dedent()
        self.pp.writeln("else")
        self.pp.indent()
        self.pp.comment('current_phase == "time"')
        self.pp.writeln("if lib.length(future_event_list) > 0 then")
        self.pp.indent()
        self.pp.writeln("timing_phase()")
        self.pp.dedent()
        self.pp.writeln("endif")
        self.pp.writeln('current_phase := "scan"')
        self.pp.dedent()
        self.pp.writeln("endif")
        self.pp.dedent()
        self.pp.writeln("endif")

        self.pp.dedent()
        self.pp.writeln("endrule")

    # =========================================================================
    # Helper methods for parsing action expressions
    # =========================================================================

    def _parse_bindings(self, bind_list: List[str]) -> List[Tuple[str, str]]:
        """
        Parse binding specifications.

        Input: ["creator_token:C", "job_token:Q"]
        Output: [("creator_token", "C"), ("job_token", "Q")]
        """
        result = []
        for bind_str in bind_list:
            parts = bind_str.split(":")
            if len(parts) == 2:
                result.append((parts[0].strip(), parts[1].strip()))
        return result

    def _translate_set_expr(self, set_expr: str) -> str:
        """
        Translate set expression to SimASM.

        Input: "job_token.service_start_time = sim_clocktime"
        Output: "service_start_time(job_token) := sim_clocktime"
        """
        # Parse entity.attr = value
        match = re.match(r'(\w+)\.(\w+)\s*=\s*(.+)', set_expr)
        if match:
            entity = match.group(1)
            attr = match.group(2)
            value = match.group(3)
            return f"{attr}({entity}) := {value}"
        return f"// Could not parse: {set_expr}"

    def _parse_arc_action(self, action_str: str, bindings: List[Tuple[str, str]]) -> List[str]:
        """
        Parse arc action string to SimASM statements.

        Syntax conventions (matching Activity Transition Table):
            Q++              - Increment marking of queue Q
            Q--              - Decrement marking of queue Q
            Q++ <- token     - Return bound token to queue Q
            Q++ <- new Type  - Create new token of Type and add to queue Q

        Token initialization is derived from token_types in the schema:
            - Attributes are auto-initialized based on type conventions
            - Real attributes with 'time' in name -> sim_clocktime
            - All tokens get auto-incrementing id

        Input: "C++ <- creator_token; Q++ <- new Job"
        Output: SimASM statements for returning/adding tokens
        """
        result = []
        parts = [p.strip() for p in action_str.split(";")]

        # Map binding names to indices
        binding_indices = {name: i for i, (name, _) in enumerate(bindings)}

        for part in parts:
            if "<-" in part:
                # Parse "Queue++ <- token" or "Queue++ <- new Type"
                match = re.match(r'(\w+)\+\+\s*<-\s*(.+)', part)
                if match:
                    queue = match.group(1)
                    source = match.group(2).strip()

                    if source.startswith("new "):
                        # Create new token - derive initialization from token_types
                        token_type = source[4:].strip()
                        var_name = f"new_{token_type.lower()}"

                        # Get token type spec from schema
                        token_spec = self.spec.token_types.get(token_type)

                        # Generate counter increment and creation
                        result.append(f"job_id_counter := job_id_counter + 1")
                        result.append(f"let {var_name} = new {token_type}")
                        result.append(f"id({var_name}) := job_id_counter")

                        # Auto-initialize attributes from token_types
                        if token_spec and token_spec.attributes:
                            for attr_name, attr_type in token_spec.attributes.items():
                                # Convention: Real attributes with 'time' in name -> sim_clocktime
                                if attr_type == "Real" and "time" in attr_name.lower():
                                    # Only set arrival_time at creation, not service_start_time
                                    if "arrival" in attr_name.lower():
                                        result.append(f"{attr_name}({var_name}) := sim_clocktime")

                        result.append(f"lib.add(tokens({queue}), {var_name})")
                        result.append(f"marking({queue}) := marking({queue}) + 1")
                    else:
                        # Return bound token
                        token_var = source
                        # Get from bound_tokens list
                        if token_var in binding_indices:
                            idx = binding_indices[token_var]
                            result.append(f"let {token_var} = lib.get(bound_tokens, {idx})")
                        result.append(f"lib.add(tokens({queue}), {token_var})")
                        result.append(f"marking({queue}) := marking({queue}) + 1")
            elif "++" in part:
                # Simple increment: Queue++
                match = re.match(r'(\w+)\+\+', part)
                if match:
                    queue = match.group(1)
                    result.append(f"marking({queue}) := marking({queue}) + 1")
            elif "--" in part:
                # Simple decrement: Queue--
                match = re.match(r'(\w+)--', part)
                if match:
                    queue = match.group(1)
                    result.append(f"marking({queue}) := marking({queue}) - 1")

        return result

    def _parse_arc_action_with_sink_detection(self, action_str: str, bindings: List[Tuple[str, str]]) -> Tuple[List[str], Optional[str]]:
        """
        Parse arc action and detect if a Job token goes to sink queue.

        Returns:
            Tuple of (action_statements, sink_job_var)
            sink_job_var is the variable name if a Job goes to sink, else None
        """
        result = []
        sink_job_var = None
        parts = [p.strip() for p in action_str.split(";")]

        # Map binding names to indices
        binding_indices = {name: i for i, (name, _) in enumerate(bindings)}

        for part in parts:
            if "<-" in part:
                match = re.match(r'(\w+)\+\+\s*<-\s*(.+)', part)
                if match:
                    queue = match.group(1)
                    source = match.group(2).strip()

                    if source.startswith("new "):
                        # Create new token
                        token_type = source[4:].strip()
                        var_name = f"new_{token_type.lower()}"
                        token_spec = self.spec.token_types.get(token_type)

                        result.append(f"job_id_counter := job_id_counter + 1")
                        result.append(f"let {var_name} = new {token_type}")
                        result.append(f"id({var_name}) := job_id_counter")

                        if token_spec and token_spec.attributes:
                            for attr_name, attr_type in token_spec.attributes.items():
                                if attr_type == "Real" and "time" in attr_name.lower():
                                    if "arrival" in attr_name.lower():
                                        result.append(f"{attr_name}({var_name}) := sim_clocktime")

                        result.append(f"lib.add(tokens({queue}), {var_name})")
                        result.append(f"marking({queue}) := marking({queue}) + 1")
                    else:
                        # Return bound token
                        token_var = source
                        if token_var in binding_indices:
                            idx = binding_indices[token_var]
                            result.append(f"let {token_var} = lib.get(bound_tokens, {idx})")
                        result.append(f"lib.add(tokens({queue}), {token_var})")
                        result.append(f"marking({queue}) := marking({queue}) + 1")

                        # Detect if this is a Job going to sink queue
                        if self.sink_queue and queue == self.sink_queue:
                            # Check if this token is a Job type
                            for bind_name, bind_queue in bindings:
                                if bind_name == token_var:
                                    queue_spec = self.spec.queues.get(bind_queue)
                                    if queue_spec and queue_spec.token_type == self.job_token_type:
                                        sink_job_var = token_var
                                    break
            elif "++" in part:
                match = re.match(r'(\w+)\+\+', part)
                if match:
                    queue = match.group(1)
                    result.append(f"marking({queue}) := marking({queue}) + 1")
            elif "--" in part:
                match = re.match(r'(\w+)--', part)
                if match:
                    queue = match.group(1)
                    result.append(f"marking({queue}) := marking({queue}) - 1")

        return result, sink_job_var

    def _translate_compute(self, compute_expr: str) -> str:
        """
        Translate compute expression to SimASM.

        Input: "time_in_system = sim_clocktime - arrival_time(job_token)"
        Output: "let time_in_system = sim_clocktime - arrival_time(job_token)"
        """
        parts = compute_expr.split("=", 1)
        if len(parts) == 2:
            var = parts[0].strip()
            expr = parts[1].strip()
            return f"let {var} = {expr}"
        return f"// Could not parse: {compute_expr}"

    def _translate_accumulate(self, acc_expr: str) -> str:
        """
        Translate accumulate expression to SimASM.

        Input: "total_sojourn_time += time_in_system"
        Output: "total_sojourn_time := total_sojourn_time + time_in_system"
        """
        match = re.match(r'(\w+)\s*\+=\s*(.+)', acc_expr)
        if match:
            var = match.group(1)
            value = match.group(2).strip()
            return f"{var} := {var} + {value}"
        return f"// Could not parse: {acc_expr}"


# =============================================================================
# PUBLIC API
# =============================================================================

def convert_acd(spec: ACDSpec) -> str:
    """Convert an ACD v2 specification to SimASM code."""
    converter = ACDConverter(spec)
    return converter.convert()


def convert_acd_from_json(json_path: str) -> str:
    """Load ACD v2 JSON and convert to SimASM code."""
    spec = load_acd_from_json(json_path)
    return convert_acd(spec)
