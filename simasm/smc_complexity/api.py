"""
Public API for SMC v10 (Semantic Model Complexity with source-rate cap).

SMC(G) = C_ctrl + Sigma_v rate(v) * deg*(v) * C(P_E,v)

Where:
- C_ctrl = 89 (fixed control overhead for next-event algorithm)
- rate(v) = min(rate_raw(v), lambda_max) -- firing rate with source-rate cap
- rate_raw(v) = Sigma_{cycles containing v} 1/T_c -- from cycle structure
- lambda_max = max source rate (from self-loop cycles)
- deg*(v) = max(1, d_in(v) + d_out(v)) -- scheduling subgraph degree
- C(P_E,v) = HET cost of event rule at vertex v

Usage:
    from simasm.smc_complexity import compute_smc

    result = compute_smc("model.simasm", "model_eg.json")
    print(f"SMC: {result.smc}")
    print(f"Control overhead: {result.control_overhead}")
    for v in result.vertex_details:
        print(f"  {v.name}: rate={v.rate:.4f}, deg={v.degree}, het={v.het_cost}, contrib={v.contribution:.2f}")
"""

import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Union

from .models import SMCResult, VertexDetail, CycleInfo
from .het_calculator import compute_event_het, C_STEP, C_PINIT, C_CTRL
from .eg_graph import parse_eg_json
from .cycle_finder import find_fundamental_cycles_multi_root


def compute_smc(
    simasm_path: Union[str, Path],
    json_spec_path: Union[str, Path],
    model_name: Optional[str] = None,
) -> SMCResult:
    """
    Compute SMC v10 via per-vertex rate decomposition.

    Pipeline:
    1. Parse .simasm -> HET per event rule (strict Nowack convention)
    2. Parse JSON -> scheduling subgraph with mean delays
    3. DFS (multi-root) -> fundamental cycles
    4. Per-vertex rate = sum(1/T_c for each cycle containing vertex)
    5. Source-rate cap: rate(v) = min(rate_raw(v), lambda_max)
    6. SMC = C_ctrl + Sigma_v rate(v) * deg*(v) * C(P_E,v)

    Args:
        simasm_path: Path to .simasm file
        json_spec_path: Path to EG JSON specification
        model_name: Optional model name (derived from filename if omitted)

    Returns:
        SMCResult with full breakdown including per-vertex details.
    """
    start = time.perf_counter()

    if model_name is None:
        model_name = Path(simasm_path).stem

    # Step 1: Compute HET costs for each event rule
    event_het = compute_event_het(simasm_path)

    # Step 2: Parse the Event Graph JSON into scheduling subgraph
    graph = parse_eg_json(json_spec_path)

    # Step 3: Find all fundamental cycles (multi-root for disconnected subgraphs)
    cycles = find_fundamental_cycles_multi_root(graph, C_STEP, event_het)

    # Step 4: Compute per-vertex firing rates from cycle structure
    vertex_rate = Counter()
    for c in cycles:
        for v in c.vertices:
            vertex_rate[v.lower()] += 1.0 / c.period

    # Propagate rates along zero-delay edges
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

    # Step 5: Source-rate cap (lambda_max from self-loop cycles)
    source_rate = 0.0
    for c in cycles:
        if len(c.vertices) == 1:
            source_rate = max(source_rate, 1.0 / c.period)

    # Step 6: Compute scheduling subgraph degree per vertex
    fan_out = Counter()
    fan_in = Counter()
    for edge in graph.edges:
        fan_out[edge.from_vertex.lower()] += 1
        fan_in[edge.to_vertex.lower()] += 1

    # Deduplicate HET values (both cased and lowered keys exist)
    het_values = {}
    seen = set()
    for name, cost in event_het.items():
        key = name.lower()
        if key not in seen:
            seen.add(key)
            het_values[name] = cost

    # Step 7: Combine into SMC v10
    c_control = C_CTRL  # 89
    vertex_details = []
    v10_sum = 0.0

    for rule_name, cost in het_values.items():
        vertex_key = rule_name.lower().replace('event_', '')
        deg = max(1, fan_out.get(vertex_key, 0) + fan_in.get(vertex_key, 0))
        rate = vertex_rate.get(vertex_key, 0.0)
        if source_rate > 0:
            rate = min(rate, source_rate)
        contribution = rate * deg * cost
        v10_sum += contribution
        vertex_details.append(VertexDetail(
            name=rule_name,
            het_cost=cost,
            rate=rate,
            degree=deg,
            contribution=contribution,
        ))

    smc = v10_sum + c_control

    elapsed = (time.perf_counter() - start) * 1000

    return SMCResult(
        model_name=model_name,
        smc=smc,
        control_overhead=c_control,
        vertex_details=vertex_details,
        event_het=event_het,
        cycles=cycles,
        num_cycles=len(cycles),
        source_rate=source_rate,
        vertex_count=len(graph.vertices),
        edge_count=len(graph.edges),
        computation_time_ms=elapsed,
    )


def compute_smc_batch(
    models: List[Dict[str, str]],
) -> List[SMCResult]:
    """
    Batch SMC v10 computation.

    Args:
        models: List of dicts with keys 'simasm_path', 'json_path',
                and optionally 'model_name'.

    Returns:
        List of SMCResult, one per model.
    """
    results = []
    for m in models:
        result = compute_smc(
            simasm_path=m["simasm_path"],
            json_spec_path=m["json_path"],
            model_name=m.get("model_name"),
        )
        results.append(result)
    return results


def get_smc_metrics(
    simasm_path: Union[str, Path],
    json_spec_path: Union[str, Path],
    model_name: Optional[str] = None,
) -> Dict:
    """
    Flat dict of all SMC v10 metrics for DataFrame construction.
    """
    r = compute_smc(simasm_path, json_spec_path, model_name)
    return {
        "model_name": r.model_name,
        "smc": r.smc,
        "control_overhead": r.control_overhead,
        "source_rate": r.source_rate,
        "num_cycles": r.num_cycles,
        "vertex_count": r.vertex_count,
        "edge_count": r.edge_count,
        "computation_time_ms": r.computation_time_ms,
    }
