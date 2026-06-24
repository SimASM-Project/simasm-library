"""
SMC Profiler: compute SMC from .simasm files alone (no JSON spec needed).

Usage:
    from simasm.smc_complexity.profiler import compute_smc_profiled

    result = compute_smc_profiled("model.simasm")
    print(f"SCR: {result.scr}")
    print(f"SMC: {result.smc}")
"""

import time
import warnings
from pathlib import Path
from typing import Optional, Union

from simasm.parser.parser import parse_file

from ..het_calculator import compute_het_from_program, C_STEP, C_INIT, C_PINIT
from ..cycle_finder import find_fundamental_cycles, find_fundamental_cycles_multi_root

from .models import ProfilerResult
from .stream_extractor import extract_streams
from .rcg_builder import build_rcg
from .rule_classifier import classify_rules
from .scheduling_graph import build_scheduling_subgraph
from .rcg_tagger import tag_rcg_streams


def compute_smc_profiled(
    simasm_path: Union[str, Path],
    model_name: Optional[str] = None,
) -> ProfilerResult:
    """
    Compute SMC from a .simasm file alone (no JSON spec needed).

    Pipeline:
    1. Parse .simasm -> Program AST
    2. Extract random streams + resolve init params
    3. Build Rule Call Graph + classify rules
    4. Build SchedulingSubgraph from AST (equivalent to JSON parse)
    5. Run existing cycle_finder on the subgraph
    6. Compute SCR + SMC using existing formulas
    """
    start = time.perf_counter()

    if model_name is None:
        model_name = Path(simasm_path).stem

    program = parse_file(str(simasm_path))

    if not program.rules and program.main_rule is None:
        raise ValueError(
            f"No rules found in '{simasm_path}'. "
            f"The file must contain at least one rule declaration."
        )

    if program.main_rule is None:
        warnings.warn(
            f"No main rule found in '{Path(simasm_path).name}'. "
            f"Rule classification will use defaults.",
            stacklevel=2,
        )

    streams = extract_streams(program)

    if not streams:
        warnings.warn(
            f"No random streams found in '{Path(simasm_path).name}'. "
            f"The scheduling subgraph will have no positive-delay edges.",
            stacklevel=2,
        )

    rcg = build_rcg(program)
    classification = classify_rules(program, rcg)
    graph = build_scheduling_subgraph(program, streams, classification, rcg)

    event_het = compute_het_from_program(program)

    for name, node in rcg.nodes.items():
        cls = classification.get(name, "recurring")
        node.is_init = cls == "init"
        node.is_recurring = cls == "recurring"
        node.is_control = cls == "control"
        node.het_cost = event_het.get(name, 0)
    tag_rcg_streams(program, rcg, streams)

    try:
        cycles = find_fundamental_cycles(graph, C_STEP, event_het)
    except ValueError:
        cycles = []

    scr = sum(c.rate for c in cycles)
    smc = C_INIT + scr * graph.t_sim

    het_values = {}
    seen = set()
    for name, cost in event_het.items():
        key = name.lower()
        if key not in seen:
            seen.add(key)
            het_values[name] = cost
    c_control = C_STEP + C_PINIT
    smc_original = sum(het_values.values()) + c_control

    from collections import Counter
    fan_out = Counter()
    fan_in = Counter()
    for edge in graph.edges:
        fan_out[edge.from_vertex.lower()] += 1
        fan_in[edge.to_vertex.lower()] += 1
    fan_weighted_sum = 0
    degree_weighted_sum = 0
    for rule_name, cost in het_values.items():
        vertex_key = rule_name.lower().replace('event_', '')
        fo_raw = fan_out.get(vertex_key, 0)
        fi_raw = fan_in.get(vertex_key, 0)
        fan = max(1, fo_raw)
        deg = max(1, fo_raw + fi_raw)
        fan_weighted_sum += fan * cost
        degree_weighted_sum += deg * cost
    smc_fan_weighted = fan_weighted_sum + c_control
    smc_degree_weighted = degree_weighted_sum + c_control
    smc_rate_structural = C_INIT + scr * smc_degree_weighted

    from collections import defaultdict
    try:
        cycles_all = find_fundamental_cycles_multi_root(graph, C_STEP, event_het)
    except ValueError:
        cycles_all = []
    vertex_rate = Counter()
    for c in cycles_all:
        for v in c.vertices:
            vertex_rate[v.lower()] += 1.0 / c.period

    adj_zero = defaultdict(list)
    for e in graph.edges:
        if e.mean_delay == 0:
            adj_zero[e.from_vertex.lower()].append(e.to_vertex.lower())
    changed = True
    while changed:
        changed = False
        for src, targets in adj_zero.items():
            if vertex_rate[src] > 0:
                for tgt in targets:
                    if vertex_rate[tgt] == 0:
                        vertex_rate[tgt] = vertex_rate[src]
                        changed = True

    # Source-rate cap: no vertex can fire faster than entities arrive
    source_rate = 0.0
    for c in cycles_all:
        if len(c.vertices) == 1:
            source_rate = max(source_rate, 1.0 / c.period)

    v10_sum = 0.0
    for rule_name, cost in het_values.items():
        vertex_key = rule_name.lower().replace('event_', '')
        deg = max(1, fan_out.get(vertex_key, 0) + fan_in.get(vertex_key, 0))
        rate = vertex_rate.get(vertex_key, 0.0)
        if source_rate > 0:
            rate = min(rate, source_rate)
        v10_sum += rate * deg * cost
    smc_per_vertex_rate = v10_sum + c_control

    # v11: throughput-capped per-vertex rate
    from .routing_matrix import build_routing_matrix
    from .flow_balance import compute_arrival_rates, compute_service_capacities
    import numpy as np

    P, s_vec, v_names = build_routing_matrix(graph)
    lambda_v = compute_arrival_rates(P, s_vec)
    mu_v = compute_service_capacities(graph, v_names)
    effective_rate = np.minimum(mu_v, lambda_v)

    v11_rate = {name.lower(): effective_rate[i] for i, name in enumerate(v_names)}
    v11_sum = 0.0
    for rule_name, cost in het_values.items():
        vertex_key = rule_name.lower().replace('event_', '')
        deg = max(1, fan_out.get(vertex_key, 0) + fan_in.get(vertex_key, 0))
        rate = v11_rate.get(vertex_key, 0.0)
        v11_sum += rate * deg * cost
    smc_v11 = v11_sum + c_control

    elapsed = (time.perf_counter() - start) * 1000

    return ProfilerResult(
        model_name=model_name,
        streams=streams,
        rcg=rcg,
        scheduling_subgraph=graph,
        cycles=cycles,
        num_cycles=len(cycles),
        scr=scr,
        smc=smc,
        t_sim=graph.t_sim,
        event_het=event_het,
        c_step=C_STEP,
        c_init=C_INIT,
        smc_original=smc_original,
        smc_fan_weighted=smc_fan_weighted,
        smc_degree_weighted=smc_degree_weighted,
        smc_rate_structural=smc_rate_structural,
        smc_per_vertex_rate=smc_per_vertex_rate,
        smc_v11=smc_v11,
        vertex_count=len(graph.vertices),
        edge_count=len(graph.edges),
        computation_time_ms=elapsed,
    )
