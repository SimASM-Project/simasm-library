"""
Generate .smc.simasm output files expressing complexity analysis results.
"""

from datetime import datetime

from .models import SMCResult


def export_smc_simasm(result: SMCResult, output_path: str) -> None:
    """Write SMC analysis results to a .smc.simasm file."""
    content = format_smc_simasm(result)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


def format_smc_simasm(result: SMCResult) -> str:
    """Format SMC analysis results as .smc.simasm text."""
    lines = []
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    lines.append(f"// Auto-generated SMC analysis for {result.model_name}")
    lines.append(f"// Computed: {ts} in {result.computation_time_ms:.2f}ms")
    lines.append("")
    lines.append(f'smc_analysis "{result.model_name}" =')
    lines.append("")

    lines.append("  // Model parameters")
    lines.append(f"  param t_sim: Real = {result.t_sim}")
    lines.append("")

    lines.append("  // HET costs per event (strict Nowack convention)")
    seen = set()
    for name, cost in sorted(result.event_het.items()):
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        lines.append(f"  het {name}: Nat = {cost}")
    lines.append("")

    lines.append("  // Control costs")
    lines.append(f"  het c_step: Nat = {result.c_step}")
    lines.append(f"  het c_init: Nat = {result.c_init}")
    lines.append("")

    lines.append("  // Fundamental cycles (from DFS)")
    for c in result.cycles:
        verts_str = ", ".join(c.vertices)
        edge_labels = [f"e({e.from_vertex}->{e.to_vertex})" for e in c.edges]
        edges_str = ", ".join(edge_labels)
        lines.append(f"  cycle c{c.index} = [{verts_str}] via [{edges_str}] with")
        lines.append(f"    cost: Nat = {c.cost}")
        lines.append(f"    period: Real = {c.period}")
        lines.append(f"    rate: Real = {c.rate:.1f}")
        lines.append(f"  endcycle")
        lines.append("")

    lines.append("  // Results")
    lines.append(f"  result scr: Real = {result.scr:.1f}")
    lines.append(f"  result smc: Real = {result.smc:.1f}")
    lines.append(f"  result smc_original: Nat = {result.smc_original}")
    lines.append(f"  result computation_time_ms: Real = {result.computation_time_ms:.2f}")
    lines.append("")
    lines.append("end_smc_analysis")
    lines.append("")

    return "\n".join(lines)
