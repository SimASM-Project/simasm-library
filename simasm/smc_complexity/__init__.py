"""
SMC Complexity v10: Per-vertex rate decomposition with source-rate cap.

Computes Semantic Model Complexity (SMC) for Event Graph models:

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
    print(f"SMC: {result.smc}")          # e.g., 403.4 for M/M/5
    print(f"C_ctrl: {result.control_overhead}")  # 89
    for v in result.vertex_details:
        print(f"  {v.name}: rate={v.rate:.4f}, deg={v.degree}, "
              f"het={v.het_cost}, contribution={v.contribution:.2f}")
"""

from .api import compute_smc, compute_smc_batch, get_smc_metrics
from .models import SMCResult, CycleInfo, VertexDetail

__all__ = [
    "compute_smc",
    "compute_smc_batch",
    "get_smc_metrics",
    "SMCResult",
    "CycleInfo",
    "VertexDetail",
]
