"""
SimASM - Abstract State Machine Framework for Discrete Event Simulation

A Python package for modeling, simulating, and verifying discrete event
systems using Abstract State Machines as the common semantic foundation.

Usage with Python API (recommended - avoids linter warnings):
    import simasm

    # Define models as strings
    simasm.register_model("mm1_eg", '''
    domain Object
    ...
    ''')

    # Run experiments
    result = simasm.run_experiment('''
    experiment Test:
        model := "mm1_eg"
        ...
    endexperiment
    ''')

    # Run verifications
    result = simasm.verify('''
    verification Check:
        models:
            import EG from "mm1_eg"
            ...
        endmodels
        ...
    endverification
    ''')

Alternative: Jupyter/Colab cell magics:
    import simasm  # Auto-registers %%simasm magic

    %%simasm model --name mm1_queue
    domain Event
    ...
"""

__version__ = "0.5.3"
__author__ = "Steve Yeo"


# Import Python API functions for direct access
from simasm.api import (
    # Model registry
    register_model,
    get_model,
    list_models,
    clear_models,
    unregister_model,
    # Experiment/verification
    run_experiment,
    verify,
    # Direct execution
    run_model,
    parse_model,
    # Conversion
    convert_model,
    # Display helpers
    display_experiment_result,
    display_verification_result,
)


# Auto-register Jupyter magics when imported in IPython/Jupyter
def _register_jupyter_magics():
    """Auto-register magics if running in IPython/Jupyter."""
    try:
        from IPython import get_ipython
        ipython = get_ipython()
        if ipython is not None:
            from simasm.jupyter.magic import SimASMMagics
            ipython.register_magics(SimASMMagics)
    except ImportError:
        pass  # IPython not installed
    except Exception:
        pass  # Not in IPython environment or other error


_register_jupyter_magics()
