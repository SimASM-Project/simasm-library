"""Compute specification-level complexity metrics: CC, LOC, KC."""

import json
import math
import zlib
from pathlib import Path


def compute_cc(json_path):
    """Cyclomatic complexity: |E| - |V| + 2p from Event Graph JSON.

    p = number of connected components (typically 1).
    """
    with open(json_path, encoding="utf-8") as f:
        spec = json.load(f)

    vertices = spec.get("vertices", spec.get("events", []))
    edges = spec.get("scheduling_edges", spec.get("edges", []))

    v_count = len(vertices)
    e_count = len(edges)

    if v_count == 0:
        return 0

    adj = {v.get("name", v.get("event_name", str(i))): set()
           for i, v in enumerate(vertices)}
    v_names = list(adj.keys())

    for edge in edges:
        src = edge.get("source", edge.get("from", ""))
        tgt = edge.get("target", edge.get("to", ""))
        if src in adj:
            adj[src].add(tgt)
        if tgt in adj:
            adj[tgt].add(src)

    visited = set()
    components = 0
    for v in v_names:
        if v not in visited:
            components += 1
            stack = [v]
            while stack:
                node = stack.pop()
                if node in visited:
                    continue
                visited.add(node)
                for neighbor in adj.get(node, []):
                    if neighbor not in visited:
                        stack.append(neighbor)

    return e_count - v_count + 2 * components


def compute_loc(simasm_path):
    """Lines of code: non-blank, non-comment lines in .simasm file."""
    count = 0
    with open(simasm_path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("//") and not stripped.startswith("#"):
                count += 1
    return count


def compute_kc(simasm_path):
    """Kolmogorov complexity approximation: log2(zlib compressed bytes)."""
    raw = Path(simasm_path).read_bytes()
    compressed = zlib.compress(raw, level=9)
    return math.log2(len(compressed)) if len(compressed) > 0 else 0.0
