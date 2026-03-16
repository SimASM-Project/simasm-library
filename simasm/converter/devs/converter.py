"""
DEVS to SimASM converter.

Converts a DEVS JSON specification into SimASM code that implements
the DEVS Abstract Simulator Algorithm (Zeigler et al. 2019).

Architecture:
  - Each atomic model maps to:
    - internal_transition_{name}() rule
    - external_transition_{name}() rule
    - output_function_{name}() rule
  - The coordinator logic maps to:
    - select_imminent() rule
    - route_output() rule
  - The main rule orchestrates one macro-step of the abstract simulator.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .schema import (
    DEVSSpec,
    AtomicModelSpec,
    InternalTransitionSpec,
    ExternalTransitionSpec,
)


def convert_devs(spec: DEVSSpec) -> str:
    """Convert a DEVS specification to SimASM source code."""
    converter = DEVSConverter(spec)
    return converter.convert()


def convert_devs_from_json(json_path: str, output_path: Optional[str] = None) -> str:
    """Load DEVS JSON and convert to SimASM. Optionally write to file."""
    spec = DEVSSpec.from_json(json_path)
    source = convert_devs(spec)
    if output_path:
        Path(output_path).write_text(source, encoding='utf-8')
    return source


class DEVSConverter:
    """Converts DEVS specification to SimASM source code."""

    def __init__(self, spec: DEVSSpec):
        self.spec = spec
        self.lines: list[str] = []
        self.indent = 0

    def convert(self) -> str:
        self.lines = []
        self._emit_header()
        self._emit_imports()
        self._emit_domains()
        self._emit_constants()
        self._emit_variables()
        self._emit_random_streams()
        self._emit_observables()
        self._emit_dynamic_functions()
        self._emit_component_rules()
        self._emit_coordinator_rules()
        self._emit_algorithm_rules()
        self._emit_init_block()
        self._emit_main_rule()
        return "\n".join(self.lines)

    # ---- helpers ----

    def _line(self, text: str = ""):
        prefix = "    " * self.indent
        self.lines.append(f"{prefix}{text}" if text else "")

    def _blank(self):
        self.lines.append("")

    def _comment(self, text: str):
        self._line(f"// {text}")

    def _section(self, title: str):
        self._blank()
        self._line(f"// {'=' * 60}")
        self._line(f"// {title}")
        self._line(f"// {'=' * 60}")
        self._blank()

    # ---- sections ----

    def _emit_header(self):
        self._line(f"// SimASM: {self.spec.model_name}")
        self._line(f"// {self.spec.description}")
        self._line(f"// Generated from DEVS specification")
        self._line(f"// Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._line(f"// Formalism: Discrete Event System Specification (DEVS)")
        self._line(f"// Algorithm: Abstract Simulator (Zeigler et al. 2019)")

    def _emit_imports(self):
        self._section("Imports")
        self._line("import Random as rnd")
        self._line("import Stdlib as lib")

    def _emit_domains(self):
        self._section("Domains")
        # Component enum (comment values for documentation)
        components = self.spec.coupled_model.components
        comp_list = ", ".join(components)
        self._comment(f"Components: {comp_list}")
        self._line("domain Component")
        self._blank()
        # Phase enums per component (comment values for documentation)
        for am in self.spec.atomic_models:
            states = ", ".join(s.name for s in am.states)
            self._comment(f"Phases: {states}")
            self._line(f"domain Phase_{am.name}")
        # Entities
        if self.spec.entities:
            self._blank()
            # Collect unique parent domains
            parents = set()
            for espec in self.spec.entities.values():
                parents.add(espec.parent)
            for parent in sorted(parents):
                self._line(f"domain {parent}")
            for ename, espec in self.spec.entities.items():
                self._line(f"domain {ename} <: {espec.parent}")

        self._blank()
        self._comment("Coordinator event type")
        self._line("domain ComponentEvent")

    def _emit_constants(self):
        self._section("Constants")
        for pname, pspec in self.spec.parameters.items():
            self._line(f"const {pname}: {pspec.type}")

    def _emit_variables(self):
        self._section("State Variables")
        self._comment("Simulation clock")
        self._line("var sim_clocktime: Real")
        self._blank()

        self._comment("Per-component phase")
        for am in self.spec.atomic_models:
            self._line(f"var phase_{am.name}: String")

        self._blank()
        self._comment("Per-component timing")
        for am in self.spec.atomic_models:
            self._line(f"var tl_{am.name}: Real")
            self._line(f"var tn_{am.name}: Real")

        self._blank()
        self._comment("Per-component state variables")
        for am in self.spec.atomic_models:
            for vname, vspec in am.state_variables.items():
                self._line(f"var {am.name}_{vname}: {vspec.type}")

        if self.spec.state_variables:
            self._blank()
            self._comment("Global state variables")
            for vname, vspec in self.spec.state_variables.items():
                self._line(f"var {vname}: {vspec.type}")

        self._blank()
        self._comment("Event list (coordinator)")
        self._line("var future_event_list: List<ComponentEvent>")

        self._blank()
        self._comment("Coordinator auxiliary variables")
        self._line("var imminent_component: String")
        self._line("var output_value: String")
        self._line("var current_input_port: String")
        self._line("var stopping_condition: Boolean")

    def _emit_random_streams(self):
        self._section("Random Streams")
        for rname, rspec in self.spec.random_streams.items():
            dist = rspec.distribution
            stream_name = rspec.stream_name if rspec.stream_name else rname
            if dist == "exponential":
                mean = rspec.params.get("mean", "1.0")
                self._line(f"var {rname}: rnd.exponential({mean}) as \"{stream_name}\"")
            elif dist == "uniform":
                a = rspec.params.get("a", "0.0")
                b = rspec.params.get("b", "1.0")
                self._line(f"var {rname}: rnd.uniform({a}, {b}) as \"{stream_name}\"")
            elif dist == "normal":
                mu = rspec.params.get("mean", "0.0")
                sigma = rspec.params.get("std", "1.0")
                self._line(f"var {rname}: rnd.normal({mu}, {sigma}) as \"{stream_name}\"")
            else:
                self._line(f"var {rname}: rnd.{dist}({', '.join(str(v) for v in rspec.params.values())}) as \"{stream_name}\"")

    def _emit_observables(self):
        if not self.spec.observables:
            return
        self._section("Observables")
        for oname, ospec in self.spec.observables.items():
            expr = self._translate_devs_expression(ospec.expression)
            self._line(f"derived function {oname}(): Real = {expr}")

    def _emit_dynamic_functions(self):
        self._section("Dynamic Function Declarations")
        self._comment("Event list entry properties")
        self._line("dynamic function cel_component(e: ComponentEvent): Component")
        self._line("dynamic function cel_time(e: ComponentEvent): Real")

    def _emit_component_rules(self):
        self._section("Component Rules (Atomic Model Transitions)")
        for am in self.spec.atomic_models:
            self._emit_internal_transition(am)
            self._blank()
            self._emit_external_transition(am)
            self._blank()
            self._emit_output_function(am)
            self._blank()

    def _emit_internal_transition(self, am: AtomicModelSpec):
        self._comment(f"Internal transition: delta_int for {am.name}")
        self._line(f"rule internal_transition_{am.name}() =")
        self.indent += 1

        transitions = am.internal_transitions
        if not transitions:
            self._line("skip")
        else:
            first = True
            for tr in transitions:
                kw = "if" if first else "elseif"
                cond_parts = [f"phase_{am.name} == \"{tr.from_state}\""]
                if tr.condition and tr.condition != "true":
                    cond_parts.append(self._qualify_condition(am.name, tr.condition))
                cond = " and ".join(cond_parts)
                self._line(f"{kw} {cond} then")
                self.indent += 1
                self._line(f"phase_{am.name} := \"{tr.to_state}\"")
                if tr.state_change:
                    for sc in tr.state_change.split(";"):
                        sc = sc.strip()
                        if sc:
                            self._line(self._qualify_state_change(am.name, sc))
                self.indent -= 1
                first = False

            self._line("endif")
            self._blank()
            self._comment("Update timing")
            self._line(f"tl_{am.name} := sim_clocktime")
            self._emit_ta_assignment(am)
        self.indent -= 1
        self._line("endrule")

    def _emit_external_transition(self, am: AtomicModelSpec):
        self._comment(f"External transition: delta_ext for {am.name}")
        self._line(f"rule external_transition_{am.name}() =")
        self.indent += 1

        transitions = am.external_transitions
        if not transitions:
            self._line("skip")
        else:
            # Check if input_port discrimination is needed
            needs_port_check = self._needs_input_port_discrimination(am)

            first = True
            for tr in transitions:
                kw = "if" if first else "elseif"
                cond_parts = [f"phase_{am.name} == \"{tr.from_state}\""]
                if needs_port_check:
                    cond_parts.append(f"current_input_port == \"{tr.input_port}\"")
                if tr.condition and tr.condition != "true":
                    cond_parts.append(self._qualify_condition(am.name, tr.condition))
                cond = " and ".join(cond_parts)
                self._line(f"{kw} {cond} then")
                self.indent += 1
                self._line(f"phase_{am.name} := \"{tr.to_state}\"")
                if tr.state_change:
                    for sc in tr.state_change.split(";"):
                        sc = sc.strip()
                        if sc:
                            self._line(self._qualify_state_change(am.name, sc))
                # Timing: only reset tn when phase actually changes
                phase_changes = (tr.from_state != tr.to_state)
                if phase_changes:
                    self._line(f"tl_{am.name} := sim_clocktime")
                    ta = self._get_time_advance(am, tr.to_state)
                    self._line(f"tn_{am.name} := sim_clocktime + {ta}")
                self.indent -= 1
                first = False

            self._line("endif")
        self.indent -= 1
        self._line("endrule")

    def _emit_output_function(self, am: AtomicModelSpec):
        self._comment(f"Output function: lambda for {am.name}")
        self._line(f"rule output_function_{am.name}() =")
        self.indent += 1

        outputs = am.output_function
        if not outputs:
            self._line("skip")
        else:
            first = True
            for out in outputs:
                kw = "if" if first else "elseif"
                cond_parts = [f"phase_{am.name} == \"{out.state}\""]
                if out.condition and out.condition != "true":
                    cond_parts.append(self._qualify_condition(am.name, out.condition))
                cond = " and ".join(cond_parts)
                self._line(f"{kw} {cond} then")
                self.indent += 1
                self._line(f"output_value := \"{out.output_port}\"")
                self.indent -= 1
                first = False

            self._line("endif")
        self.indent -= 1
        self._line("endrule")

    def _emit_coordinator_rules(self):
        self._section("Coordinator Rules")
        self._emit_select_imminent()
        self._blank()
        self._emit_route_output()
        self._blank()
        self._emit_update_event_list()

    def _emit_select_imminent(self):
        self._comment("Select imminent component: sort event list, pop earliest (tie-break by Select priority)")
        self._line("rule select_imminent() =")
        self.indent += 1
        self._comment("Sort event list by scheduled time (stable sort preserves Select priority)")
        self._line("lib.sort(future_event_list, \"cel_time\")")
        self._blank()
        self._comment("Pop imminent (earliest) event")
        self._line("let imminent_event = lib.pop(future_event_list)")
        self._line("imminent_component := cel_component(imminent_event)")
        self._blank()
        self._comment("Advance clock to event time")
        self._line("sim_clocktime := cel_time(imminent_event)")
        self.indent -= 1
        self._line("endrule")

    def _emit_route_output(self):
        self._comment("Route output from imminent component to influenced receivers")
        self._line("rule route_output() =")
        self.indent += 1

        couplings = self.spec.coupled_model.internal_couplings
        if not couplings:
            self._line("skip")
        else:
            # Group couplings by source model
            by_source: dict[str, list] = {}
            for c in couplings:
                by_source.setdefault(c.from_model, []).append(c)

            first_src = True
            for src_model, src_couplings in by_source.items():
                kw = "if" if first_src else "elseif"
                self._line(f"{kw} imminent_component == \"{src_model}\" then")
                self.indent += 1

                # Check if source has multiple output ports
                ports = set(c.from_port for c in src_couplings)
                if len(ports) <= 1:
                    # Single port - route all unconditionally
                    for c in src_couplings:
                        self._comment(f"Route: {c.from_model}.{c.from_port} -> {c.to_model}.{c.to_port}")
                        self._line(f"current_input_port := \"{c.to_port}\"")
                        self._line(f"external_transition_{c.to_model}()")
                else:
                    # Multiple ports - condition on output_value
                    by_port: dict[str, list] = {}
                    for c in src_couplings:
                        by_port.setdefault(c.from_port, []).append(c)

                    first_port = True
                    for port, port_couplings in by_port.items():
                        pkw = "if" if first_port else "elseif"
                        self._line(f"{pkw} output_value == \"{port}\" then")
                        self.indent += 1
                        for c in port_couplings:
                            self._comment(f"Route: {c.from_model}.{c.from_port} -> {c.to_model}.{c.to_port}")
                            self._line(f"current_input_port := \"{c.to_port}\"")
                            self._line(f"external_transition_{c.to_model}()")
                        self.indent -= 1
                        first_port = False
                    self._line("endif")

                self.indent -= 1
                first_src = False

            self._line("endif")
        self.indent -= 1
        self._line("endrule")

    def _emit_update_event_list(self):
        self._comment("Rebuild event list from current tn values (Select priority order for tie-breaking)")
        self._line("rule update_event_list() =")
        self.indent += 1
        self._line("future_event_list := []")
        self._blank()
        # Add in Select priority order so stable sort preserves priority for ties
        for comp in self.spec.coupled_model.select_priority:
            self._line(f"let evt_{comp} = new ComponentEvent")
            self._line(f"cel_component(evt_{comp}) := \"{comp}\"")
            self._line(f"cel_time(evt_{comp}) := tn_{comp}")
            self._line(f"lib.add(future_event_list, evt_{comp})")
            self._blank()
        self.indent -= 1
        self._line("endrule")

    def _emit_algorithm_rules(self):
        self._section("Abstract Simulator Algorithm")
        self._emit_initialisation()
        self._blank()
        self._emit_simulator_step()

    def _emit_initialisation(self):
        self._comment("Initialization: send (i, t0) to all component simulators")
        self._line("rule initialisation_routine() =")
        self.indent += 1
        self._line("sim_clocktime := 0.0")
        self._blank()

        for am in self.spec.atomic_models:
            self._comment(f"Initialize {am.name}")
            self._line(f"phase_{am.name} := \"{am.initial_state}\"")
            self._line(f"tl_{am.name} := 0.0")
            init_ta = self._get_time_advance(am, am.initial_state)
            self._line(f"tn_{am.name} := {init_ta}")
            for vname, vspec in am.state_variables.items():
                self._line(f"{am.name}_{vname} := {vspec.initial}")
            self._blank()

        for vname, vspec in self.spec.state_variables.items():
            self._line(f"{vname} := {vspec.initial}")

        self._line("stopping_condition := false")

        self._blank()
        self._comment("Initialize event list")
        self._line("future_event_list := []")
        for comp in self.spec.coupled_model.select_priority:
            self._line(f"let evt_{comp} = new ComponentEvent")
            self._line(f"cel_component(evt_{comp}) := \"{comp}\"")
            self._line(f"cel_time(evt_{comp}) := tn_{comp}")
            self._line(f"lib.add(future_event_list, evt_{comp})")

        self.indent -= 1
        self._line("endrule")

    def _emit_simulator_step(self):
        self._comment("One macro-step of the Abstract Simulator")
        self._line("rule simulator_step() =")
        self.indent += 1

        self._comment("Phase 1: Select imminent and advance time (sort FEL, pop earliest)")
        self._line("select_imminent()")

        self._blank()
        self._comment("Phase 2: Output function (lambda) then internal transition (delta_int)")
        self._line("output_value := \"\"")
        first = True
        components = self.spec.coupled_model.components
        for comp in components:
            kw = "if" if first else "elseif"
            self._line(f"{kw} imminent_component == \"{comp}\" then")
            self.indent += 1
            self._line(f"output_function_{comp}()")
            self._line(f"internal_transition_{comp}()")
            self.indent -= 1
            first = False
        self._line("endif")

        self._blank()
        self._comment("Phase 3: Route output to receivers (only if lambda produced output)")
        self._line("if output_value != \"\" then")
        self.indent += 1
        self._line("route_output()")
        self.indent -= 1
        self._line("endif")

        self._blank()
        self._comment("Phase 4: Rebuild event list with updated tn values")
        self._line("update_event_list()")

        self._blank()
        self._comment("Phase 5: Check stopping condition")
        self._line(f"if {self._translate_devs_expression(self.spec.stopping_condition)} then")
        self.indent += 1
        self._line("stopping_condition := true")
        self.indent -= 1
        self._line("endif")

        self.indent -= 1
        self._line("endrule")

    def _emit_init_block(self):
        self._section("Initialization Block")
        self._line("init:")
        self.indent += 1
        for pname, pspec in self.spec.parameters.items():
            self._line(f"{pname} := {pspec.value}")
        self._blank()
        self._line("future_event_list := []")
        self._line("initialisation_routine()")
        self.indent -= 1
        self._line("endinit")

    def _emit_main_rule(self):
        self._section("Main Rule")
        self._line("main rule main =")
        self.indent += 1
        self._line("if not stopping_condition then")
        self.indent += 1
        self._line("simulator_step()")
        self.indent -= 1
        self._line("else")
        self.indent += 1
        self._line("skip")
        self.indent -= 1
        self._line("endif")
        self.indent -= 1
        self._line("endrule")

    # ---- utility methods ----

    def _get_time_advance(self, am: AtomicModelSpec, state_name: str) -> str:
        """Get the time advance expression for a given state."""
        for s in am.states:
            if s.name == state_name:
                ta = s.time_advance
                if ta == "infinity" or ta == float('inf'):
                    return "999999999.0"
                elif isinstance(ta, (int, float)):
                    return str(float(ta))
                else:
                    return str(ta)
        return "999999999.0"

    def _emit_ta_assignment(self, am: AtomicModelSpec):
        """Emit an if-block that sets tn_{name} based on current phase."""
        if len(am.states) == 1:
            ta = self._get_time_advance(am, am.states[0].name)
            self._line(f"tn_{am.name} := sim_clocktime + {ta}")
            return

        for i, s in enumerate(am.states):
            ta = self._get_time_advance(am, s.name)
            if i == 0:
                self._line(f"if phase_{am.name} == \"{s.name}\" then")
            elif i == len(am.states) - 1:
                self._line("else")
            else:
                self._line(f"elseif phase_{am.name} == \"{s.name}\" then")
            self.indent += 1
            self._line(f"tn_{am.name} := sim_clocktime + {ta}")
            self.indent -= 1
        self._line("endif")

    def _qualify_condition(self, model_name: str, condition: str) -> str:
        """Qualify state variable references in a condition with the model name prefix."""
        am = self._get_atomic_model(model_name)
        if am is None:
            return condition
        result = condition
        for vname in am.state_variables:
            result = result.replace(vname, f"{model_name}_{vname}")
        # Also replace parameter references (these are global, no prefix)
        return result

    def _qualify_state_change(self, model_name: str, state_change: str) -> str:
        """Qualify state variable references in a state change with the model name prefix."""
        am = self._get_atomic_model(model_name)
        if am is None:
            return state_change
        result = state_change
        for vname in am.state_variables:
            result = result.replace(vname, f"{model_name}_{vname}")
        return result

    def _translate_devs_expression(self, expr: str) -> str:
        """Translate DEVS observable expressions (e.g., 'Server_1.queue_count')."""
        result = expr
        for am in self.spec.atomic_models:
            for vname in am.state_variables:
                result = result.replace(f"{am.name}.{vname}", f"{am.name}_{vname}")
        return result

    def _needs_input_port_discrimination(self, am: AtomicModelSpec) -> bool:
        """Check if model has multiple input_ports for the same from_state."""
        from collections import defaultdict
        ports_by_state: dict[str, set] = defaultdict(set)
        for tr in am.external_transitions:
            ports_by_state[tr.from_state].add(tr.input_port)
        return any(len(ports) > 1 for ports in ports_by_state.values())

    def _get_atomic_model(self, name: str) -> Optional[AtomicModelSpec]:
        for am in self.spec.atomic_models:
            if am.name == name:
                return am
        return None
