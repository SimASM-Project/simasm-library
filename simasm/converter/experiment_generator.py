"""
Experiment File Generator

Generates SimASM experiment files (.simasm) from model specifications.
Includes common statistics templates for queueing systems.
"""

from typing import List, Dict, Optional, Union
from pathlib import Path
from .codegen.pretty_printer import PrettyPrinter


class ExperimentGenerator:
    """
    Generates SimASM experiment files with common statistics.
    """

    # Common statistics templates for queueing systems
    QUEUEING_STATISTICS = {
        "L_q": {
            "type": "time_average",
            "expression_eg": "queue_count(queue)",
            "expression_acd": "marking(Q)",
            "description": "Average queue length (L_q)"
        },
        "L": {
            "type": "time_average",
            "expression_eg": "queue_count(queue) + service_count(server)",
            "expression_acd": "marking(Q) + (num_servers - marking(S))",
            "description": "Average number in system (L)"
        },
        "throughput": {
            "type": "count",
            "expression_eg": "departure_count(server)",
            "expression_acd": "departure_count",
            "description": "Total departures"
        },
        "utilization": {
            "type": "time_average",
            "expression_eg": "service_count(server) / service_capacity",
            "expression_acd": "(num_servers - marking(S)) / num_servers",
            "description": "Server utilization (rho)"
        },
    }

    def __init__(self, model_path: str, experiment_name: str):
        self.model_path = model_path
        self.experiment_name = experiment_name
        self.pp = PrettyPrinter()

    def generate(
        self,
        formalism: str = "eg",  # "eg" for Event Graph, "acd" for ACD
        replication_count: int = 10,
        warmup_time: float = 100.0,
        run_length: float = 1000.0,
        base_seed: int = 12345,
        statistics: Optional[List[str]] = None,
        output_format: str = "csv",
        output_path: Optional[str] = None
    ) -> str:
        """
        Generate an experiment file.

        Args:
            formalism: "eg" for Event Graph expressions, "acd" for ACD expressions
            replication_count: Number of replications
            warmup_time: Warm-up period before collecting statistics
            run_length: Total simulation run length
            base_seed: Base random seed
            statistics: List of statistic names to include (defaults to all)
            output_format: Output format ("json", "csv", "md")
            output_path: Optional output file path

        Returns:
            Experiment file content as string
        """
        self.pp.reset()

        if statistics is None:
            statistics = list(self.QUEUEING_STATISTICS.keys())

        if output_path is None:
            output_path = f"{self.experiment_name}_results.{output_format}"

        self._write_header()
        self._write_experiment_start()
        self._write_model_declaration()
        self._write_replication_block(replication_count, warmup_time, run_length, base_seed)
        self._write_statistics_block(statistics, formalism)
        self._write_output_block(output_format, output_path)
        self._write_experiment_end()

        return self.pp.get_output()

    def _write_header(self):
        """Write file header."""
        self.pp.block_comment(f"Experiment: {self.experiment_name}")
        self.pp.comment(f"Model: {self.model_path}")
        self.pp.comment("Generated experiment file with common queueing statistics")
        self.pp.blank()

    def _write_experiment_start(self):
        """Write experiment block start."""
        self.pp.line(f"experiment {self.experiment_name}:")

    def _write_model_declaration(self):
        """Write model declaration."""
        self.pp.indent()
        self.pp.line(f'model := "{self.model_path}"')
        self.pp.blank()

    def _write_replication_block(
        self,
        count: int,
        warmup: float,
        length: float,
        seed: int
    ):
        """Write replication settings block."""
        self.pp.line("replication:")
        self.pp.indent()
        self.pp.line(f"count: {count}")
        self.pp.line(f"warm_up_time: {warmup}")
        self.pp.line(f"run_length: {length}")
        self.pp.line('seed_strategy: "incremental"')
        self.pp.line(f"base_seed: {seed}")
        self.pp.dedent()
        self.pp.line("endreplication")
        self.pp.blank()

    def _write_statistics_block(self, statistics: List[str], formalism: str):
        """Write statistics block."""
        self.pp.line("statistics:")
        self.pp.indent()

        expr_key = f"expression_{formalism}"

        for stat_name in statistics:
            if stat_name in self.QUEUEING_STATISTICS:
                stat = self.QUEUEING_STATISTICS[stat_name]
                self.pp.line(f"stat {stat_name}: {stat['type']}")
                self.pp.indent()

                # Use the appropriate expression for the formalism
                expression = stat.get(expr_key, stat.get("expression_eg"))
                self.pp.line(f'expression: "{expression}"')

                if stat.get("description"):
                    self.pp.comment(stat["description"])

                self.pp.dedent()
                self.pp.line("endstat")
                self.pp.blank()

        self.pp.dedent()
        self.pp.line("endstatistics")
        self.pp.blank()

    def _write_output_block(self, format: str, path: str):
        """Write output settings block."""
        self.pp.line("output:")
        self.pp.indent()
        self.pp.line(f'format: "{format}"')
        self.pp.line(f'file_path: "{path}"')
        self.pp.dedent()
        self.pp.line("endoutput")

    def _write_experiment_end(self):
        """Write experiment block end."""
        self.pp.dedent()
        self.pp.line("endexperiment")


def generate_experiment(
    model_path: str,
    experiment_name: str,
    formalism: str = "eg",
    **kwargs
) -> str:
    """
    Convenience function to generate an experiment file.

    Args:
        model_path: Path to the model file
        experiment_name: Name for the experiment
        formalism: "eg" or "acd"
        **kwargs: Additional arguments passed to ExperimentGenerator.generate()

    Returns:
        Experiment file content as string
    """
    generator = ExperimentGenerator(model_path, experiment_name)
    return generator.generate(formalism=formalism, **kwargs)


def generate_verification_experiment(
    model1_path: str,
    model2_path: str,
    experiment_name: str,
    seed: int = 42,
    output_path: Optional[str] = None
) -> str:
    """
    Generate a verification experiment comparing two models.

    Args:
        model1_path: Path to first model (e.g., Event Graph)
        model2_path: Path to second model (e.g., ACD)
        experiment_name: Name for the verification
        seed: Random seed for deterministic comparison
        output_path: Optional output file path

    Returns:
        Verification file content as string
    """
    pp = PrettyPrinter()

    if output_path is None:
        output_path = f"{experiment_name}_results.csv"

    pp.block_comment(f"Verification: {experiment_name}")
    pp.comment(f"Comparing: {model1_path} vs {model2_path}")
    pp.comment("Stutter equivalence verification for trace equivalence")
    pp.blank()

    pp.line(f"verification {experiment_name}:")
    pp.indent()

    # Models block
    pp.line("models:")
    pp.indent()
    pp.line(f'import M1 := "{model1_path}"')
    pp.line(f'import M2 := "{model2_path}"')
    pp.dedent()
    pp.line("endmodels")
    pp.blank()

    # Seed
    pp.line(f"seed: {seed}")
    pp.blank()

    # Labels block - observable state predicates
    pp.line("labels:")
    pp.indent()

    # Queue count labels
    for i in range(6):
        pp.line(f'label Q{i} for M1: "queue_count(queue) == {i}"')
        pp.line(f'label Q{i} for M2: "marking(Q) == {i}"')

    pp.line('label Q_ge6 for M1: "queue_count(queue) >= 6"')
    pp.line('label Q_ge6 for M2: "marking(Q) >= 6"')
    pp.blank()

    # Servers busy labels
    for i in range(6):
        pp.line(f'label B{i} for M1: "service_count(server) == {i}"')
        pp.line(f'label B{i} for M2: "(num_servers - marking(S)) == {i}"')

    pp.dedent()
    pp.line("endlabels")
    pp.blank()

    # Observables block
    pp.line("observables:")
    pp.indent()
    for i in range(6):
        pp.line(f"observable queue_{i}: M1->Q{i}, M2->Q{i}")
    pp.line("observable queue_ge6: M1->Q_ge6, M2->Q_ge6")
    for i in range(6):
        pp.line(f"observable busy_{i}: M1->B{i}, M2->B{i}")
    pp.dedent()
    pp.line("endobservables")
    pp.blank()

    # Check block
    pp.line("check:")
    pp.indent()
    pp.line('type: "stutter_equivalence"')
    pp.dedent()
    pp.line("endcheck")
    pp.blank()

    # Output block
    pp.line("output:")
    pp.indent()
    pp.line('format: "csv"')
    pp.line(f'file_path: "{output_path}"')
    pp.dedent()
    pp.line("endoutput")

    pp.dedent()
    pp.line("endverification")

    return pp.get_output()


# Example usage
if __name__ == "__main__":
    # Generate Event Graph experiment
    eg_exp = generate_experiment(
        model_path="mm5_eg.simasm",
        experiment_name="MM5_EG_Experiment",
        formalism="eg",
        replication_count=30,
        warmup_time=100.0,
        run_length=1000.0
    )
    print("Event Graph Experiment:")
    print(eg_exp)
    print()

    # Generate ACD experiment
    acd_exp = generate_experiment(
        model_path="mm5_acd.simasm",
        experiment_name="MM5_ACD_Experiment",
        formalism="acd",
        replication_count=30,
        warmup_time=100.0,
        run_length=1000.0
    )
    print("ACD Experiment:")
    print(acd_exp)
    print()

    # Generate verification experiment
    ver_exp = generate_verification_experiment(
        model1_path="mm5_eg.simasm",
        model2_path="mm5_acd.simasm",
        experiment_name="MM5_Verification"
    )
    print("Verification Experiment:")
    print(ver_exp)
