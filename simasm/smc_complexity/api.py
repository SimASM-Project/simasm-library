"""
Public API for SMC cycle-rate complexity analysis.

Usage:
    from simasm.smc_complexity import compute_smc

    result = compute_smc("model.simasm", "model_eg.json")
    print(f"SCR: {result.scr}")
    print(f"SMC: {result.smc}")
"""

import time
from pathlib import Path
from typing import Dict, List, Optional, Union

from .models import SMCResult
from .het_calculator import compute_event_het, C_STEP, C_INIT, C_PINIT
from .eg_graph import parse_eg_json
from .cycle_finder import find_fundamental_cycles
from .smc_spec import export_smc_simasm


def compute_smc(
    simasm_path: Union[str, Path],
    json_spec_path: Union[str, Path],
    model_name: Optional[str] = None,
    t_sim: Optional[float] = None,
) -> SMCResult:
    """
    Compute SMC via DFS cycle-rate decomposition.

    1. Parse .simasm → HET per event rule (strict Nowack)
    2. Parse JSON → scheduling subgraph + mean delays
    3. DFS → fundamental cycles
    4. SCR = Σ C(c_k)/T(c_k), SMC = C_init + SCR × T_sim

    Args:
        simasm_path: Path to .simasm file
        json_spec_path: Path to EG JSON specification
        model_name: Optional model name (derived from filename if omitted)
        t_sim: Override simulation end time (from JSON if omitted)

    Returns:
        SMCResult with full breakdown and timing.
    """
    start = time.perf_counter()

    if model_name is None:
        model_name = Path(simasm_path).stem

    event_het = compute_event_het(simasm_path)
    graph = parse_eg_json(json_spec_path)

    if t_sim is None:
        t_sim = graph.t_sim

    cycles = find_fundamental_cycles(graph, C_STEP, event_het)

    scr = sum(c.rate for c in cycles)
    smc = C_INIT + scr * t_sim

    het_values = {}
    seen = set()
    for name, cost in event_het.items():
        key = name.lower()
        if key not in seen:
            seen.add(key)
            het_values[name] = cost
    c_control = C_STEP + C_PINIT
    smc_original = sum(het_values.values()) + c_control

    elapsed = (time.perf_counter() - start) * 1000

    return SMCResult(
        model_name=model_name,
        event_het=event_het,
        c_step=C_STEP,
        c_init=C_INIT,
        cycles=cycles,
        num_cycles=len(cycles),
        scr=scr,
        smc=smc,
        t_sim=t_sim,
        smc_original=smc_original,
        computation_time_ms=elapsed,
        vertex_count=len(graph.vertices),
        edge_count=len(graph.edges),
    )


def compute_smc_batch(
    models: List[Dict[str, str]],
) -> List[SMCResult]:
    """
    Batch SMC computation.

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
    Flat dict of all SMC metrics for DataFrame construction.
    """
    r = compute_smc(simasm_path, json_spec_path, model_name)
    return {
        "model_name": r.model_name,
        "scr": r.scr,
        "smc": r.smc,
        "smc_original": r.smc_original,
        "t_sim": r.t_sim,
        "c_step": r.c_step,
        "c_init": r.c_init,
        "num_cycles": r.num_cycles,
        "vertex_count": r.vertex_count,
        "edge_count": r.edge_count,
        "computation_time_ms": r.computation_time_ms,
    }
