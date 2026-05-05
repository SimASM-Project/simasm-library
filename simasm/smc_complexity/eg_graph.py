"""
Parse Event Graph JSON specification into a scheduling subgraph.
"""

import json
from pathlib import Path
from typing import Union

from .models import SchedulingEdge, SchedulingSubgraph
from .delay_resolver import resolve_mean_delay


def parse_eg_json(json_path: Union[str, Path]) -> SchedulingSubgraph:
    """
    Parse an Event Graph JSON spec into a SchedulingSubgraph.

    Extracts vertices, scheduling edges, random streams, parameters,
    and resolves mean delays for each edge.
    """
    path = Path(json_path)
    with open(path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    vertices = [v["name"] for v in spec["vertices"]]

    params_raw = spec.get("parameters", {})
    parameters = {}
    for name, info in params_raw.items():
        val = info.get("value")
        if val is not None:
            try:
                parameters[name] = float(val)
            except (ValueError, TypeError):
                pass

    random_streams = {}
    streams_raw = spec.get("random_streams", {})
    for stream_name, stream_info in streams_raw.items():
        random_streams[stream_name] = {
            "distribution": stream_info["distribution"],
            "params": stream_info.get("params", {}),
        }

    edges = []
    for e in spec.get("scheduling_edges", []):
        delay_expr = str(e.get("delay", "0"))
        mean_delay = resolve_mean_delay(delay_expr, random_streams, parameters)
        edge = SchedulingEdge(
            from_vertex=e["from"],
            to_vertex=e["to"],
            delay_expr=delay_expr,
            condition=e.get("condition", "true"),
            priority=e.get("priority", 0),
            mean_delay=mean_delay,
        )
        edges.append(edge)

    adjacency = {v: [] for v in vertices}
    for e in edges:
        if e.from_vertex in adjacency:
            adjacency[e.from_vertex].append(e)

    initial_events = spec.get("initial_events", [])
    source_vertex = initial_events[0]["event"] if initial_events else vertices[0]

    t_sim = parameters.get("sim_end_time", 10000.0)

    return SchedulingSubgraph(
        vertices=vertices,
        edges=edges,
        adjacency=adjacency,
        source_vertex=source_vertex,
        random_streams=random_streams,
        parameters=parameters,
        t_sim=t_sim,
    )
