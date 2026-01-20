"""
SimASM Jupyter Integration

Provides magic commands for interactive SimASM usage in Jupyter notebooks.

Usage:
    import simasm  # Auto-registers magics

    # Or explicitly:
    from simasm.jupyter import register_model, list_models, clear_models

Functions:
    register_model(name, source) - Register an in-memory model
    get_model(name) - Get model source by name
    list_models() - List all registered model names
    clear_models() - Clear all registered models
"""

from .magic import (
    register_model,
    get_model,
    list_models,
    clear_models,
    get_model_registry,
    SimASMMagics,
    load_ipython_extension,
)

__all__ = [
    "register_model",
    "get_model",
    "list_models",
    "clear_models",
    "get_model_registry",
    "SimASMMagics",
    "load_ipython_extension",
]
