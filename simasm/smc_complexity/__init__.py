"""
SMC Complexity: Cycle-rate decomposition for Event Graph models.

Computes Semantic Model Complexity (SMC) via DFS fundamental cycle
detection on the scheduling subgraph, using strict Nowack HET convention.

    SMC(G) = C_init + SCR(G) × T_sim
    SCR(G) = Σ C(c_k) / T(c_k)

Usage:
    from simasm.smc_complexity import compute_smc

    result = compute_smc("model.simasm", "model_eg.json")
"""

from .api import compute_smc, compute_smc_batch, get_smc_metrics
from .smc_spec import export_smc_simasm
from .models import SMCResult, CycleInfo

__all__ = [
    "compute_smc",
    "compute_smc_batch",
    "get_smc_metrics",
    "export_smc_simasm",
    "SMCResult",
    "CycleInfo",
]
