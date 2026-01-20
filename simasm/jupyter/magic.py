"""
jupyter/magic.py

Jupyter magic commands for SimASM.

Provides cell magics for defining models, running experiments, and
running verifications directly in Jupyter notebooks.

Usage:
    import simasm  # Auto-registers magics

    %%simasm model --name mm1_queue
    domain Event
    domain Load
    ...

    %%simasm experiment
    experiment Test:
        model := "mm1_queue"
        ...
    endexperiment

    %%simasm verify
    verification Check:
        models:
            import EG from "mm1_eg"
            import ACD from "mm1_acd"
        ...
    endverification
"""

import argparse
import shlex
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, Optional, Union

try:
    from IPython.core.magic import Magics, magics_class, cell_magic, line_magic
    from IPython.display import display, HTML, Markdown
    IPYTHON_AVAILABLE = True
except ImportError:
    IPYTHON_AVAILABLE = False
    # Create dummy classes for when IPython is not available
    class Magics:
        def __init__(self, shell=None):
            self.shell = shell

    def magics_class(cls):
        return cls

    def cell_magic(name):
        def decorator(func):
            return func
        return decorator

    def line_magic(name):
        def decorator(func):
            return func
        return decorator


# Import the shared model registry from api module
# This ensures %%simasm magic and simasm.register_model() use the same registry
from simasm.api import (
    register_model,
    get_model,
    list_models,
    clear_models,
)

# For backwards compatibility, also expose a getter for the registry
def get_model_registry() -> Dict[str, str]:
    """Get the global model registry."""
    from simasm.api import _model_registry
    return _model_registry


@magics_class
class SimASMMagics(Magics):
    """
    Jupyter magic commands for SimASM.

    Provides:
    - %%simasm model --name NAME: Define an in-memory model
    - %%simasm experiment: Run an experiment specification
    - %%simasm verify: Run a verification specification
    - %simasm_models: List registered models
    - %simasm_clear: Clear all registered models
    """

    def __init__(self, shell=None):
        super().__init__(shell)
        self._temp_dir = None

    @cell_magic
    def simasm(self, line: str, cell: str):
        """
        Main cell magic for SimASM.

        Usage:
            %%simasm model --name mymodel
            <model code>

            %%simasm experiment
            <experiment spec>

            %%simasm verify
            <verification spec>
        """
        # Parse the command line
        args = shlex.split(line)

        if not args:
            return self._display_help()

        command = args[0].lower()

        if command == "model":
            return self._handle_model(args[1:], cell)
        elif command == "experiment":
            return self._handle_experiment(args[1:], cell)
        elif command == "verify":
            return self._handle_verification(args[1:], cell)
        elif command == "convert":
            return self._handle_convert(args[1:], cell)
        else:
            return self._display_error(f"Unknown command: {command}")

    @line_magic
    def simasm_models(self, line: str):
        """List all registered models."""
        models = list_models()
        if not models:
            print("No models registered.")
        else:
            print("Registered models:")
            for name in models:
                source = get_model(name)
                lines = source.strip().split('\n')
                preview = lines[0][:50] + "..." if len(lines[0]) > 50 else lines[0]
                print(f"  - {name}: {preview}")

    @line_magic
    def simasm_clear(self, line: str):
        """Clear all registered models."""
        count = len(list_models())
        clear_models()
        print(f"Cleared {count} model(s).")

    def _handle_model(self, args: list, cell: str):
        """Handle %%simasm model --name NAME"""
        parser = argparse.ArgumentParser(prog='%%simasm model')
        parser.add_argument('--name', '-n', required=True, help='Model name')

        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return

        name = parsed.name
        register_model(name, cell)

        # Display confirmation
        lines = cell.strip().split('\n')
        line_count = len(lines)

        self._display_success(
            f"Model '{name}' registered",
            f"{line_count} lines of SimASM code"
        )

    def _handle_experiment(self, args: list, cell: str):
        """Handle %%simasm experiment"""
        from simasm.experimenter.transformer import ExperimentParser
        from simasm.experimenter.engine import ExperimenterEngine
        from simasm.experimenter.ast import ExperimentNode

        try:
            # Parse experiment specification
            parser = ExperimentParser()
            spec = parser.parse(cell)

            # Check if model is in registry
            model_path = spec.model_path
            if get_model(model_path) is not None:
                # Use in-memory model - write to temp file
                return self._run_experiment_with_memory_model(spec, model_path)
            else:
                # Model is a file path
                engine = ExperimenterEngine(spec)

                def progress(rep_id, total):
                    print(f"  Replication {rep_id}/{total}...", end='\r')

                result = engine.run(progress_callback=progress)
                print()  # Clear progress line

                return self._display_experiment_result(result)

        except Exception as e:
            return self._display_error(f"Experiment error: {e}")

    def _run_experiment_with_memory_model(self, spec, model_name: str):
        """Run experiment using an in-memory model."""
        from simasm.experimenter.engine import ExperimenterEngine
        from simasm.experimenter.ast import ExperimentNode

        model_source = get_model(model_name)

        # Create temp directory if needed
        if self._temp_dir is None:
            self._temp_dir = tempfile.mkdtemp(prefix="simasm_")

        # Write model to temp file
        model_file = Path(self._temp_dir) / f"{model_name}.simasm"
        model_file.write_text(model_source, encoding='utf-8')

        # Update spec to use temp file path
        spec.model_path = str(model_file)

        # Run experiment
        engine = ExperimenterEngine(spec, base_path=Path(self._temp_dir))

        def progress(rep_id, total):
            print(f"  Replication {rep_id}/{total}...", end='\r')

        result = engine.run(progress_callback=progress)
        print()  # Clear progress line

        return self._display_experiment_result(result)

    def _handle_verification(self, args: list, cell: str):
        """Handle %%simasm verify"""
        from simasm.experimenter.transformer import VerificationParser
        from simasm.experimenter.engine import VerificationEngine

        try:
            # Parse verification specification
            parser = VerificationParser()
            spec = parser.parse(cell)

            # Check if models are in registry and prepare temp files
            models_in_registry = []
            for model_import in spec.models:
                if get_model(model_import.path) is not None:
                    models_in_registry.append(model_import)

            if models_in_registry:
                return self._run_verification_with_memory_models(spec)
            else:
                # All models are file paths
                engine = VerificationEngine(spec)

                def progress(model_name, message):
                    print(f"  {model_name}: {message}")

                result = engine.run(progress_callback=progress)

                return self._display_verification_result(result)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._display_error(f"Verification error: {e}")

    def _run_verification_with_memory_models(self, spec):
        """Run verification using in-memory models."""
        from simasm.experimenter.engine import VerificationEngine

        # Create temp directory if needed
        if self._temp_dir is None:
            self._temp_dir = tempfile.mkdtemp(prefix="simasm_")

        # Write each in-memory model to temp file
        for model_import in spec.models:
            model_source = get_model(model_import.path)
            if model_source is not None:
                model_file = Path(self._temp_dir) / f"{model_import.path}.simasm"
                model_file.write_text(model_source, encoding='utf-8')
                model_import.path = str(model_file)

        # Run verification
        engine = VerificationEngine(spec, base_path=Path(self._temp_dir))

        def progress(model_name, message):
            print(f"  {model_name}: {message}")

        result = engine.run(progress_callback=progress)

        return self._display_verification_result(result)

    def _handle_convert(self, args: list, cell: str):
        """Handle %%simasm convert"""
        from simasm.converter.engine import ConvertEngine, format_output
        from simasm.converter.parser import ConvertParser
        from simasm.api import _model_registry

        try:
            # Determine base path for file resolution
            # Try to get notebook directory, fall back to cwd
            base_path = Path.cwd()
            if self.shell is not None:
                try:
                    # Try to get the notebook's directory
                    notebook_path = self.shell.user_ns.get('__session__', None)
                    if notebook_path:
                        base_path = Path(notebook_path).parent
                except Exception:
                    pass

            # Parse and execute
            engine = ConvertEngine(base_path=base_path, model_registry=_model_registry)
            parser = ConvertParser()
            specs = parser.parse(cell)

            results = engine.execute(cell)

            # Display results
            for i, result in enumerate(results):
                spec = specs[i]
                output = format_output(result, spec.print_lines)
                self._display_convert_result(result, output, spec.print_lines)

            # Return the last result for programmatic access
            return results[-1] if results else None

        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._display_error(f"Convert error: {e}")

    def _display_convert_result(self, result, output: str, print_lines):
        """Display convert result."""
        if not IPYTHON_AVAILABLE:
            print(output)
            return

        # Build HTML
        html = ['<div style="margin: 10px 0;">']

        # Header with success badge
        html.append('<p style="font-size: 1.1em;">')
        html.append('<span style="background: #28a745; color: white; padding: 4px 12px; border-radius: 4px; font-weight: bold;">')
        html.append(f'&#10004; Converted: {result.name}')
        html.append('</span>')
        html.append('</p>')

        # Info
        if result.registered_as:
            html.append(f'<p><strong>Registered as:</strong> {result.registered_as}</p>')
        if result.output_path:
            html.append(f'<p><strong>Written to:</strong> {result.output_path}</p>')

        # Code preview (if printing enabled)
        if print_lines is not False:
            code_lines = result.simasm_code.split('\n')
            total_lines = len(code_lines)

            if print_lines is True:
                display_lines = code_lines
                truncated = False
            else:
                display_lines = code_lines[:print_lines]
                truncated = total_lines > print_lines

            html.append('<pre style="background: #1e1e1e; color: #d4d4d4; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 0.9em;">')
            html.append('\n'.join(display_lines))
            if truncated:
                html.append(f'\n// ... ({total_lines - print_lines} more lines)')
            html.append('</pre>')

        html.append('</div>')

        display(HTML('\n'.join(html)))

    def _display_experiment_result(self, result):
        """Display experiment result as rich HTML."""
        if not IPYTHON_AVAILABLE:
            return self._display_experiment_result_text(result)

        # Build HTML table
        html = ['<div style="margin: 10px 0;">']
        html.append('<h4>Experiment Results</h4>')
        html.append(f'<p><strong>Replications:</strong> {len(result.replications)}</p>')
        html.append(f'<p><strong>Total time:</strong> {result.total_wall_time:.2f}s</p>')

        # Summary table
        if result.summary:
            html.append('<table style="border-collapse: collapse; margin: 10px 0;">')
            html.append('<tr style="background: #f0f0f0;">')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">Statistic</th>')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">Mean</th>')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">Std Dev</th>')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">95% CI</th>')
            html.append('</tr>')

            for name, stats in result.summary.items():
                html.append('<tr>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{name}</td>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{stats.mean:.4f}</td>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{stats.std_dev:.4f}</td>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">[{stats.ci_lower:.4f}, {stats.ci_upper:.4f}]</td>')
                html.append('</tr>')

            html.append('</table>')

        html.append('</div>')

        display(HTML('\n'.join(html)))
        return result

    def _display_experiment_result_text(self, result):
        """Display experiment result as text (fallback)."""
        print("=" * 60)
        print("EXPERIMENT RESULTS")
        print("=" * 60)
        print(f"Replications: {len(result.replications)}")
        print(f"Total time: {result.total_wall_time:.2f}s")
        print()

        if result.summary:
            print(f"{'Statistic':<25} {'Mean':>12} {'Std Dev':>12} {'95% CI':>25}")
            print("-" * 60)
            for name, stats in result.summary.items():
                ci = f"[{stats.ci_lower:.4f}, {stats.ci_upper:.4f}]"
                print(f"{name:<25} {stats.mean:>12.4f} {stats.std_dev:>12.4f} {ci:>25}")

        return result

    def _display_verification_result(self, result):
        """Display verification result as rich HTML."""
        if not IPYTHON_AVAILABLE:
            return self._display_verification_result_text(result)

        # Check if multi-seed verification
        is_multi_seed = hasattr(result, 'num_seeds') and result.num_seeds > 1

        # Determine status color
        if result.is_equivalent:
            status_color = "#28a745"  # Green
            status_text = "EQUIVALENT"
            status_icon = "&#10004;"  # Checkmark
        else:
            status_color = "#dc3545"  # Red
            status_text = "NOT EQUIVALENT"
            status_icon = "&#10008;"  # X mark

        # Build HTML
        html = ['<div style="margin: 10px 0;">']
        html.append('<h4>Verification Results</h4>')

        # Status badge
        html.append(f'<p style="font-size: 1.2em;">')
        html.append(f'<span style="background: {status_color}; color: white; padding: 4px 12px; border-radius: 4px; font-weight: bold;">')
        html.append(f'{status_icon} {status_text}')
        html.append('</span>')
        html.append('</p>')

        html.append(f'<p><strong>Time elapsed:</strong> {result.time_elapsed:.3f}s</p>')
        html.append(f'<p>{result.message}</p>')

        # Multi-seed summary
        if is_multi_seed:
            html.append(f'<p><strong>Seeds tested:</strong> {result.num_seeds}</p>')
            html.append(f'<p><strong>Seeds passed:</strong> {result.equivalent_count}/{result.num_seeds}</p>')
            if result.failed_seeds:
                html.append(f'<p><strong>Failed seeds:</strong> {result.failed_seeds}</p>')

        # Model stats table
        if result.model_stats:
            html.append('<table style="border-collapse: collapse; margin: 10px 0;">')
            html.append('<tr style="background: #f0f0f0;">')
            html.append('<th style="border: 1px solid #ddd; padding: 8px;">Model</th>')
            if is_multi_seed:
                html.append('<th style="border: 1px solid #ddd; padding: 8px;">Avg Raw Trace</th>')
                html.append('<th style="border: 1px solid #ddd; padding: 8px;">Avg No-Stutter</th>')
            else:
                html.append('<th style="border: 1px solid #ddd; padding: 8px;">Raw Trace</th>')
                html.append('<th style="border: 1px solid #ddd; padding: 8px;">No-Stutter</th>')
                html.append('<th style="border: 1px solid #ddd; padding: 8px;">Stutter Steps</th>')
            html.append('</tr>')

            for name, stats in result.model_stats.items():
                html.append('<tr>')
                html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{name}</td>')
                raw_len = stats.get("raw_length", stats.get("avg_raw_length", "?"))
                ns_len = stats.get("ns_length", stats.get("avg_ns_length", "?"))
                if isinstance(raw_len, float):
                    html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{raw_len:.1f}</td>')
                else:
                    html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{raw_len}</td>')
                if isinstance(ns_len, float):
                    html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{ns_len:.1f}</td>')
                else:
                    html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{ns_len}</td>')
                if not is_multi_seed:
                    html.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{stats.get("stutter_steps", "?")}</td>')
                html.append('</tr>')

            html.append('</table>')

        html.append('</div>')

        display(HTML('\n'.join(html)))
        return result

    def _display_verification_result_text(self, result):
        """Display verification result as text (fallback)."""
        print("=" * 60)
        print("VERIFICATION RESULTS")
        print("=" * 60)

        if result.is_equivalent:
            print("[PASS] EQUIVALENT")
        else:
            print("[FAIL] NOT EQUIVALENT")

        print(f"Time elapsed: {result.time_elapsed:.3f}s")
        print(result.message)
        print()

        if result.model_stats:
            print(f"{'Model':<20} {'Raw':>10} {'No-Stutter':>12} {'Stutter':>10}")
            print("-" * 60)
            for name, stats in result.model_stats.items():
                print(f"{name:<20} {stats.get('raw_length', '?'):>10} {stats.get('ns_length', '?'):>12} {stats.get('stutter_steps', '?'):>10}")

        return result

    def _display_success(self, title: str, message: str):
        """Display success message."""
        if IPYTHON_AVAILABLE:
            html = f'''
            <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 4px; padding: 10px; margin: 5px 0;">
                <strong style="color: #155724;">&#10004; {title}</strong>
                <p style="margin: 5px 0 0 0; color: #155724;">{message}</p>
            </div>
            '''
            display(HTML(html))
        else:
            print(f"[OK] {title}: {message}")

    def _display_error(self, message: str):
        """Display error message."""
        if IPYTHON_AVAILABLE:
            html = f'''
            <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; padding: 10px; margin: 5px 0;">
                <strong style="color: #721c24;">&#10008; Error</strong>
                <p style="margin: 5px 0 0 0; color: #721c24;">{message}</p>
            </div>
            '''
            display(HTML(html))
        else:
            print(f"[ERROR] {message}")

    def _display_help(self):
        """Display help message."""
        help_text = """
        SimASM Jupyter Magic Commands:

        %%simasm model --name NAME
            Define an in-memory model with the given name.

        %%simasm experiment
            Run an experiment specification.

        %%simasm verify
            Run a verification specification.

        %%simasm convert
            Convert JSON specification to SimASM code.
            Example:
                convert mm5_eg:
                    source: "mm5_eg.json"
                    formalism: event_graph
                    register: "mm5_eg"
                    print: 50
                endconvert

        %simasm_models
            List all registered in-memory models.

        %simasm_clear
            Clear all registered models.
        """
        print(help_text)


def load_ipython_extension(ipython):
    """
    Load the SimASM IPython extension.

    Called when user runs: %load_ext simasm.jupyter.magic
    """
    ipython.register_magics(SimASMMagics)


def _auto_register_magics():
    """
    Auto-register magics if running in IPython/Jupyter.

    Called when simasm package is imported.
    """
    if not IPYTHON_AVAILABLE:
        return

    try:
        from IPython import get_ipython
        ipython = get_ipython()
        if ipython is not None:
            ipython.register_magics(SimASMMagics)
    except Exception:
        pass  # Silently fail if not in IPython
