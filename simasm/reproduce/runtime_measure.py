"""Measure simulation runtime via o2despy_eg EventGraphModel."""

import time
from datetime import timedelta
from pathlib import Path

from simasm.o2despy_eg import EventGraphModel

SEEDS = [
    42, 123, 456, 789, 1024, 2048, 3333, 4096, 5555, 6174,
    7777, 8192, 9001, 9999, 10007, 11111, 12345, 13579, 14000, 15013,
    16384, 17171, 18000, 19937, 20000, 21212, 22222, 23456, 24680, 25000,
]


def measure_runtime(json_path, num_reps=30, run_length=10000):
    """Measure mean wall-clock runtime over multiple replications.

    Args:
        json_path: Path to Event Graph JSON specification.
        num_reps: Number of replications.
        run_length: Simulation horizon in time units.

    Returns:
        dict with runtime_mean, runtime_std, runtime_min, runtime_max.
    """
    json_path = str(json_path)
    runtimes = []
    for seed in SEEDS[:num_reps]:
        model = EventGraphModel.from_json(json_path, seed=seed)
        t0 = time.perf_counter()
        model.run(duration=timedelta(hours=run_length))
        runtimes.append(time.perf_counter() - t0)

    import statistics
    return {
        "runtime_mean": statistics.mean(runtimes),
        "runtime_std": statistics.stdev(runtimes) if len(runtimes) > 1 else 0.0,
        "runtime_min": min(runtimes),
        "runtime_max": max(runtimes),
        "num_reps": len(runtimes),
    }
