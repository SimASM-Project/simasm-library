"""
Extract random stream declarations and resolve init parameters from a Program AST.
"""

from typing import Dict, Optional, Tuple

from simasm.parser.ast import Program, RndStreamType
from simasm.core.terms import LiteralTerm, LocationTerm, VariableTerm
from simasm.core.rules import UpdateStmt, SeqStmt

from .models import StreamInfo


DISTRIBUTION_MEAN_FN = {
    "exponential": lambda vals: vals[0],
    "uniform": lambda vals: (vals[0] + vals[1]) / 2,
    "triangular": lambda vals: (vals[0] + vals[1] + vals[2]) / 3,
    "normal": lambda vals: vals[0],
    "lognormal": lambda vals: vals[0],
    "constant": lambda vals: vals[0],
}


def extract_streams(program: Program) -> Dict[str, StreamInfo]:
    """
    Extract rnd.* stream declarations from Program.variables.
    Resolve parameter values from the init block.
    """
    init_params = resolve_init_params(program)
    streams = {}

    for var_decl in program.variables:
        if not isinstance(var_decl.type_expr, RndStreamType):
            continue

        rnd_type = var_decl.type_expr
        param_exprs = tuple(_term_to_name(a) for a in rnd_type.arguments)
        param_values = tuple(_resolve_param(expr, init_params) for expr in param_exprs)
        mean = compute_distribution_mean(rnd_type.distribution, param_values)

        streams[var_decl.name] = StreamInfo(
            var_name=var_decl.name,
            distribution=rnd_type.distribution,
            param_exprs=param_exprs,
            param_values=param_values,
            stream_name=_clean_stream_name(rnd_type.stream_name),
            mean_delay=mean,
        )

    return streams


def resolve_init_params(program: Program) -> Dict[str, float]:
    """
    Walk InitBlock.body for UpdateStmt nodes.
    Collect {location_name: float_value} for simple constant assignments.
    """
    if program.init is None:
        return {}

    params: Dict[str, float] = {}
    _collect_init_params(program.init.body, params)
    return params


def compute_distribution_mean(distribution: str, param_values: Tuple[float, ...]) -> float:
    """
    Compute the mean of a distribution given resolved parameter values.
    Raises ValueError for unknown distributions.
    """
    fn = DISTRIBUTION_MEAN_FN.get(distribution)
    if fn is None:
        raise ValueError(
            f"Unsupported distribution: '{distribution}'. "
            f"Supported: {list(DISTRIBUTION_MEAN_FN.keys())}"
        )
    return fn(param_values)


def _collect_init_params(stmt, params: Dict[str, float]):
    if isinstance(stmt, SeqStmt):
        for s in stmt.statements:
            _collect_init_params(s, params)
    elif isinstance(stmt, UpdateStmt):
        loc = stmt.location
        if not isinstance(loc, LocationTerm):
            return
        name = loc.func_name
        if isinstance(stmt.value, LiteralTerm):
            val = stmt.value.value
            if isinstance(val, (int, float)):
                params[name] = float(val)


def _clean_stream_name(raw: Optional[str]) -> Optional[str]:
    """Work around parser bug where stream_name is mangled LiteralTerm repr.

    The Lark transformer's rnd_stream_type_named uses str(items[3])[1:-1]
    to strip quotes, but items[3] is a LiteralTerm so str() gives
    "Literal('arrivals')" and [1:-1] yields mangled output.
    """
    # TODO: Remove once RndStreamType.stream_name returns plain str
    if raw is None:
        return None
    import re
    m = re.search(r"'([^']+)'", raw)
    if m:
        return m.group(1)
    return raw


def _term_to_name(term) -> str:
    if isinstance(term, VariableTerm):
        return term.name
    if isinstance(term, LocationTerm):
        return term.func_name
    if isinstance(term, LiteralTerm):
        return str(term.value)
    return str(term)


def _resolve_param(expr_name: str, init_params: Dict[str, float]) -> float:
    try:
        return float(expr_name)
    except ValueError:
        pass
    if expr_name in init_params:
        return init_params[expr_name]
    raise ValueError(
        f"Cannot resolve parameter '{expr_name}'. "
        f"Available init params: {list(init_params.keys())}"
    )
