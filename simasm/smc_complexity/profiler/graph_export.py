"""
Export RCG + scheduling subgraph as DOT, Mermaid, and JSON.

Serves paper figures (DOT → PDF/SVG), draft previews (Mermaid),
and programmatic consumption (JSON).
"""

from typing import Dict, List, Optional

from ..het_calculator import C_INIT
from ..models import SchedulingSubgraph, CycleInfo
from .models import StreamInfo, RuleCallGraph


def export_dot(
    rcg: RuleCallGraph,
    scheduling_subgraph: SchedulingSubgraph,
    cycles: List[CycleInfo],
    streams: Dict[str, StreamInfo],
    title: str = "",
) -> str:
    scr = sum(c.rate for c in cycles)
    smc = scr * scheduling_subgraph.t_sim + C_INIT

    header = f'digraph RCG {{\n    rankdir=TB;\n    label="{title} — SCR={scr:.1f}, SMC={smc:,.0f}";\n'
    header += '    node [fontname="Helvetica", fontsize=10];\n\n'

    stream_rules = _stream_anchored_rules(rcg, streams)

    init_nodes = []
    recurring_nodes = []
    control_nodes = []
    for name, node in sorted(rcg.nodes.items()):
        if node.is_init:
            init_nodes.append((name, node))
        elif node.is_control:
            control_nodes.append((name, node))
        else:
            recurring_nodes.append((name, node))

    lines = [header]

    if init_nodes:
        lines.append('    subgraph cluster_init {')
        lines.append('        label="init"; style=dashed; color=grey;')
        for name, node in init_nodes:
            lines.append(f'        {_dot_id(name)} {_dot_node_attrs(name, node, stream_rules)};')
        lines.append('    }\n')

    for name, node in control_nodes:
        lines.append(f'    {_dot_id(name)} {_dot_node_attrs(name, node, stream_rules)};')

    if recurring_nodes:
        lines.append('')
        for name, node in recurring_nodes:
            lines.append(f'    {_dot_id(name)} {_dot_node_attrs(name, node, stream_rules)};')

    lines.append('')

    for edge in rcg.edges:
        attrs = []
        if edge.is_dispatch:
            attrs.append('style=dashed')
        if edge.guard:
            attrs.append(f'label="{edge.guard}"')
        attr_str = f' [{", ".join(attrs)}]' if attrs else ''
        lines.append(f'    {_dot_id(edge.from_rule)} -> {_dot_id(edge.to_rule)}{attr_str};')

    lines.append('')
    lines.append('    // Scheduling subgraph edges')
    for edge in scheduling_subgraph.edges:
        label = f'{edge.mean_delay:.2f}' if edge.mean_delay > 0 else '0'
        cond = f'\\n[{edge.condition}]' if edge.condition != 'true' else ''
        lines.append(
            f'    {_dot_id(edge.from_vertex)} -> {_dot_id(edge.to_vertex)} '
            f'[label="{label}{cond}", color=blue, fontcolor=blue];'
        )

    lines.append('}')
    return '\n'.join(lines)


def export_mermaid(
    rcg: RuleCallGraph,
    scheduling_subgraph: SchedulingSubgraph,
    cycles: List[CycleInfo],
    streams: Dict[str, StreamInfo],
) -> str:
    lines = ['graph TD']

    stream_rules = _stream_anchored_rules(rcg, streams)

    for name, node in sorted(rcg.nodes.items()):
        mid = _mermaid_id(name)
        label = f'{name}\\nHET={node.het_cost}'
        if node.is_control:
            lines.append(f'    {mid}{{{{{label}}}}}')
        elif node.is_init:
            lines.append(f'    {mid}([{label}])')
        else:
            lines.append(f'    {mid}[{label}]')

    lines.append('')

    for edge in rcg.edges:
        src = _mermaid_id(edge.from_rule)
        dst = _mermaid_id(edge.to_rule)
        if edge.is_dispatch:
            if edge.guard:
                lines.append(f'    {src} -.->|{edge.guard}| {dst}')
            else:
                lines.append(f'    {src} -.-> {dst}')
        else:
            if edge.guard:
                lines.append(f'    {src} -->|{edge.guard}| {dst}')
            else:
                lines.append(f'    {src} --> {dst}')

    lines.append('')
    lines.append('    %% Scheduling subgraph edges')
    for edge in scheduling_subgraph.edges:
        src = _mermaid_id(edge.from_vertex)
        dst = _mermaid_id(edge.to_vertex)
        label = f'{edge.mean_delay:.2f}' if edge.mean_delay > 0 else '0'
        lines.append(f'    {src} -->|{label}| {dst}')

    lines.append('')
    lines.append('    classDef init fill:#e8f5e9,stroke:#4caf50;')
    lines.append('    classDef recurring fill:#e3f2fd,stroke:#2196f3;')
    lines.append('    classDef control fill:#fff3e0,stroke:#ff9800;')

    init_ids = []
    recurring_ids = []
    control_ids = []
    for name, node in rcg.nodes.items():
        mid = _mermaid_id(name)
        if node.is_init:
            init_ids.append(mid)
        elif node.is_control:
            control_ids.append(mid)
        else:
            recurring_ids.append(mid)

    if init_ids:
        lines.append(f'    class {",".join(sorted(init_ids))} init;')
    if recurring_ids:
        lines.append(f'    class {",".join(sorted(recurring_ids))} recurring;')
    if control_ids:
        lines.append(f'    class {",".join(sorted(control_ids))} control;')

    return '\n'.join(lines)


def export_graph_json(
    rcg: RuleCallGraph,
    scheduling_subgraph: SchedulingSubgraph,
    cycles: List[CycleInfo],
    streams: Dict[str, StreamInfo],
) -> dict:
    scr = sum(c.rate for c in cycles)
    smc = scr * scheduling_subgraph.t_sim + C_INIT

    rcg_nodes = []
    for name, node in sorted(rcg.nodes.items()):
        ntype = "init" if node.is_init else ("control" if node.is_control else "recurring")
        rcg_nodes.append({
            "name": name,
            "het": node.het_cost,
            "type": ntype,
            "streams": node.streams,
        })

    rcg_edges = []
    for edge in rcg.edges:
        rcg_edges.append({
            "from": edge.from_rule,
            "to": edge.to_rule,
            "guard": edge.guard,
            "dispatch": edge.is_dispatch,
        })

    sched_edges = []
    for edge in scheduling_subgraph.edges:
        sched_edges.append({
            "from": edge.from_vertex,
            "to": edge.to_vertex,
            "delay": edge.mean_delay,
            "condition": edge.condition,
        })

    cycle_list = []
    for c in cycles:
        cycle_list.append({
            "index": c.index,
            "vertices": c.vertices,
            "cost": c.cost,
            "period": c.period,
            "rate": c.rate,
        })

    return {
        "rcg_nodes": rcg_nodes,
        "rcg_edges": rcg_edges,
        "scheduling_vertices": list(scheduling_subgraph.vertices),
        "scheduling_edges": sched_edges,
        "cycles": cycle_list,
        "summary": {
            "scr": scr,
            "smc": smc,
            "t_sim": scheduling_subgraph.t_sim,
        },
    }


def _dot_id(name: str) -> str:
    return name.replace(" ", "_").replace("-", "_")


def _dot_node_attrs(name: str, node, stream_rules: Dict[str, List[str]]) -> str:
    if node.is_control:
        shape = 'diamond'
    elif node.is_init:
        shape = 'ellipse'
    else:
        shape = 'box'

    label = f'{name}\\nHET={node.het_cost}'
    attrs = [f'shape={shape}', f'label="{label}"']

    if name in stream_rules:
        stream_label = ', '.join(stream_rules[name])
        attrs.append(f'penwidth=2, xlabel="{stream_label}"')

    return '[' + ', '.join(attrs) + ']'


def _mermaid_id(name: str) -> str:
    return name.replace(" ", "_").replace("-", "_")


def _stream_anchored_rules(rcg: RuleCallGraph, streams: Dict[str, StreamInfo]) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for name, node in rcg.nodes.items():
        if node.streams:
            result[name] = node.streams
    return result


