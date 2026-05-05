"""
Resolve edge delay expressions to their expected (mean) values.

Supports:
- Numeric literals: 0, 5.0
- Random stream names: "interarrival_time" -> look up distribution mean
- Parameter names: "setup_time" -> look up parameter value
"""

from typing import Dict


DISTRIBUTION_MEAN = {
    "exponential": lambda params: _param_value(params, "mean"),
    "uniform": lambda params: (_param_value(params, "min") + _param_value(params, "max")) / 2,
    "triangular": lambda params: (
        _param_value(params, "min") + _param_value(params, "mode") + _param_value(params, "max")
    ) / 3,
    "constant": lambda params: _param_value(params, "value"),
    "normal": lambda params: _param_value(params, "mean"),
    "lognormal": lambda params: _param_value(params, "mean"),
}


def _param_value(params: dict, key: str) -> float:
    """Extract a numeric value from distribution params dict."""
    val = params.get(key, 0)
    if isinstance(val, (int, float)):
        return float(val)
    return 0.0


def resolve_mean_delay(
    delay_expr: str,
    random_streams: Dict[str, dict],
    parameters: Dict[str, float],
) -> float:
    """
    Resolve a delay expression to its mean value.

    Resolution order:
    1. Numeric literal -> float(value)
    2. Random stream name -> distribution mean
    3. Parameter name -> parameter value
    4. Unknown -> 0.0
    """
    delay_expr = delay_expr.strip()

    try:
        return float(delay_expr)
    except ValueError:
        pass

    if delay_expr in random_streams:
        stream = random_streams[delay_expr]
        dist = stream["distribution"]
        params = stream.get("params", {})
        resolved_params = {}
        for k, v in params.items():
            if isinstance(v, str) and v in parameters:
                resolved_params[k] = parameters[v]
            elif isinstance(v, (int, float)):
                resolved_params[k] = float(v)
            else:
                resolved_params[k] = 0.0
        mean_fn = DISTRIBUTION_MEAN.get(dist)
        if mean_fn:
            return mean_fn(resolved_params)
        return 0.0

    if delay_expr in parameters:
        return parameters[delay_expr]

    return 0.0
