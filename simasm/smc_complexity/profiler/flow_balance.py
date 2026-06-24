"""
Flow balance solver for computing steady-state arrival rates.

Solves: λ = (I - P^T)^{-1} × s

Also computes service capacity vector μ_v = 1/d̄_v.
"""

import warnings
from typing import List

import numpy as np

from ..models import SchedulingSubgraph


def compute_arrival_rates(P: np.ndarray, s: np.ndarray) -> np.ndarray:
    """
    Solve flow balance: λ = (I - P^T)^{-1} × s

    Returns λ vector (arrival rate at each vertex).

    For fork-join models with broadcast (row sums > 1), the matrix may be
    singular or near-singular. Uses lstsq as fallback for robust solution.
    """
    n = P.shape[0]
    A = np.eye(n) - P.T

    try:
        lam = np.linalg.solve(A, s)
    except np.linalg.LinAlgError:
        # Fallback: least-squares solution for singular/near-singular systems
        # This handles fork-join + feedback where spectral radius = 1.0 exactly
        lam, residuals, rank, sv = np.linalg.lstsq(A, s, rcond=None)
        if rank < n:
            warnings.warn(
                f"Flow balance matrix is rank-deficient (rank={rank}/{n}). "
                f"Using least-squares solution.",
                stacklevel=2,
            )

    # Sanity: arrival rates should be non-negative
    if np.any(lam < -1e-10):
        warnings.warn(
            f"Flow balance produced negative arrival rates "
            f"(min={lam.min():.6f}). Clamping to zero.",
            stacklevel=2,
        )
        lam = np.maximum(lam, 0.0)

    return lam


def compute_service_capacities(
    graph: SchedulingSubgraph,
    vertex_names: List[str],
) -> np.ndarray:
    """
    Compute μ_v = 1/d̄_v for each vertex.

    - Source vertices (self-loop): μ = inf (self-loop is inter-arrival, not service)
    - Non-self-loop outgoing edge with delay > 0: μ = 1/delay
    - Sink vertices (no outgoing edges) or zero-delay only: μ = inf
    """
    n = len(vertex_names)
    mu = np.full(n, np.inf)
    idx = {v: i for i, v in enumerate(vertex_names)}

    # Identify source vertices (have self-loops)
    source_vertices = set()
    for e in graph.edges:
        if e.from_vertex == e.to_vertex and e.mean_delay > 0:
            source_vertices.add(e.from_vertex)

    for e in graph.edges:
        # Skip self-loops (they define source rate, not service capacity)
        if e.from_vertex == e.to_vertex:
            continue
        # Skip zero-delay edges (instantaneous routing)
        if e.mean_delay <= 0:
            continue
        # This edge defines a service capacity for its from_vertex
        v_idx = idx.get(e.from_vertex)
        if v_idx is not None:
            # Take the minimum if multiple service edges exist
            mu[v_idx] = min(mu[v_idx], 1.0 / e.mean_delay)

    return mu
