# SimASM

**Abstract State Machine Framework for Discrete-Event Simulation**

SimASM is a programming language and verification framework that enables:
- Writing discrete-event simulation models using a clean DSL
- Supporting multiple DES formalisms (Event Graph, Activity Cycle Diagram)
- Verifying behavioral equivalence between models via stutter equivalence
- Running experiments with statistics collection and automatic plotting

## Overview

SimASM adopts Abstract State Machines (ASM) as the semantic foundation for DES.
This enables precise translation of DES formalisms into a common formal language,
allowing rigorous verification of behavioral equivalence across formalisms.

**Key Concepts:**
- **Event Graph (EG)**: Event-based formalism using next-event time-advance algorithm
- **Activity Cycle Diagram (ACD)**: Activity-based formalism using three-phase scanning
- **Stutter Equivalence**: Two models are equivalent if they produce the same
  sequence of observable state changes, regardless of internal steps

## Installation

```bash
# From PyPI (recommended)
pip install simasm

# From source (development)
git clone https://github.com/SimASM-Project/simasm-library.git
cd simasm-library
pip install -e .
```

**Requirements:** Python 3.9+

## Reproducing Paper Results

SimASM includes a reproducibility module for the SMC paper:

> Yeo, K. S. S., & Li, H. (2025). Semantic Model Complexity for Event Graph
> Discrete-Event Simulation Models via Abstract State Machines. *SIMULTECH 2025*.

### Experiment 1: 51-Model LOOCV Validation (Section 5)

```bash
simasm-reproduce loocv
```

Runs the full 51-model benchmark (~5 min). Measures simulation runtimes live
(30 replications each), computes SMC/CC/LOC/KC, and performs leave-one-out
cross-validation on three pools (27 homogeneous, 24 heterogeneous, 51 combined).

### Experiment 2: Warehouse Case Study (Section 6)

```bash
simasm-reproduce warehouse
```

Trains log-log regression on the 51-model pool and predicts runtime for an
industrial warehouse model. Reports absolute percentage errors and 95%
prediction intervals for all four metrics.

### Run Both

```bash
simasm-reproduce all
```

### Expected Output

Runtimes will vary across machines, but the relative rankings (Q², sign test
results) should be consistent with the paper:
- SMC Q² ≈ 0.95 on the combined 51-model pool
- SMC sign test: 51/51 wins vs CC/LOC/KC (p < 0.0001)
- Warehouse: only SMC's 95% prediction interval contains the actual runtime

Use `-v` for verbose per-model output:
```bash
simasm-reproduce loocv -v
```

### Benchmark Models

The 51 models are included in `simasm/models/` (JSON) and `simasm/models_simasm/`
(.simasm translations):
- **27 homogeneous**: tandem, fork-join, feedback × 9 sizes (1-20 stations)
- **24 heterogeneous**: 3 topologies × 2 sizes × 2 IST patterns × 2 IAT levels
- **1 warehouse**: 6-station industrial warehouse (out-of-sample case study)

## Quick Start

### Option 1: Run a Jupyter Notebook
```bash
pip install simasm[jupyter]
jupyter notebook notebooks/simasm_demo.ipynb
```

### Option 2: Python API
```python
import simasm

# Register a model
simasm.register_model("mm5_eg", open("simasm/input/models/mm5_eg.simasm").read())

# Run an experiment
result = simasm.run_experiment('''
experiment Test:
    model := "mm5_eg"
    replications: 10
    run_length: 1000.0
endexperiment
''')
```

### Option 3: Command Line
```bash
# Run experiment
python -m simasm.experimenter.cli simasm/input/experiments/littles_law_eg.simasm

# Run verification
python -m simasm.experimenter.cli --verify simasm/input/experiments/mm5_verification.simasm
```

## Repository Structure

```
simasm-library/
├── notebooks/               # Interactive tutorials and examples
├── simasm/
│   ├── models/              # 51 benchmark EG JSON specifications
│   ├── models_simasm/       # 51 benchmark SimASM translations
│   ├── smc_complexity/      # SMC v10 metric computation
│   ├── o2despy_eg/          # Event Graph simulation engine
│   ├── reproduce/           # Paper reproducibility CLI
│   ├── complexity/          # General complexity analysis
│   ├── converter/           # JSON-to-SimASM conversion
│   ├── core/                # ASM term/state/rule representation
│   ├── experimenter/        # Experiment & verification CLI
│   ├── parser/              # SimASM parser
│   ├── runtime/             # ASM execution engine
│   ├── simulation/          # Experiment runner & statistics
│   ├── verification/        # Stutter equivalence verification
│   ├── input/
│   │   ├── models/          # Pre-built .simasm model files
│   │   └── experiments/     # Experiment & verification specs
│   └── output/              # Generated results (JSON, CSV, PNG)
├── pyproject.toml
└── README.md
```

## Notebooks Guide

| Notebook | Description | Recommended Order |
|----------|-------------|-------------------|
| `simasm_demo.ipynb` | Interactive intro using Jupyter magic commands | 1 |
| `simasm_python_api_demo.ipynb` | Python API alternative to magics | 1 |
| `eg_littles_law.ipynb` | Event Graph + Little's Law verification | 2 |
| `acd_littles_law.ipynb` | ACD + Little's Law verification | 2 |
| `eg_to_asm_translation.ipynb` | Formal EG→ASM translation algorithm | 3 |
| `acd_to_asm_translation.ipynb` | Formal ACD→ASM translation algorithm | 3 |
| `mm5_verification.ipynb` | Stutter equivalence verification (M/M/5) | 4 |
| `warehouse_verification.ipynb` | Complex 6-station warehouse verification | 5 |
| `warehouse_verification_w_analysis.ipynb` | Extended statistical analysis | 5 |

## Input Files

### Models (`simasm/input/models/`)
| File | Description |
|------|-------------|
| `mm5_eg.simasm` | M/M/5 queue using Event Graph formalism |
| `mm5_acd.simasm` | M/M/5 queue using Activity Cycle Diagram |
| `warehouse_eg.simasm` | 6-station warehouse outbound process (EG) |
| `warehouse_acd.simasm` | 6-station warehouse outbound process (ACD) |

### Experiments (`simasm/input/experiments/`)
| File | Description |
|------|-------------|
| `littles_law_eg.simasm` | Little's Law verification (L = λW) for EG |
| `littles_law_acd.simasm` | Little's Law verification for ACD |
| `mm5_verification.simasm` | Stutter equivalence: EG vs ACD |
| `warehouse_w_stutter_equivalence.simasm` | Warehouse model verification |

## Output Files

Outputs are saved to `simasm/output/` with timestamped directories:

```
simasm/output/
└── 2026-01-19_20-14-21_ExperimentName/
    ├── ExperimentName_results.json   # Statistics
    ├── boxplots.png                  # Box plots
    ├── summary_statistics.png        # Bar charts with CIs
    └── timeseries.png                # Time series traces
```

### JSON Output Structure
```json
{
  "experiment": "LittlesLawEG",
  "metadata": {
    "num_replications": 30,
    "total_wall_time": 7.522,
    "generated_at": "2026-01-19T18:34:06"
  },
  "replications": [
    {
      "id": 1,
      "seed": 12345,
      "final_time": 1000.49,
      "steps_taken": 3239,
      "statistics": {
        "L_system": 2.05,
        "rho_utilization": 0.40
      }
    }
  ]
}
```

## Two DES Formalisms

### Event Graph (EG)
- Event-based: focuses on events and scheduling relationships
- Uses next-event time-advance algorithm
- Events trigger other events with delays and conditions

### Activity Cycle Diagram (ACD)
- Activity-based: focuses on activities and resource flows
- Uses three-phase scanning algorithm (scan → time → execute)
- Activities consume and produce tokens from queues

## Stutter Equivalence Verification

SimASM can verify that two models (e.g., EG and ACD of the same system)
produce identical observable behavior:

```
verification EG_ACD_Equivalence:
    models:
        import EG from "mm5_eg"
        import ACD from "mm5_acd"
    seed: 42
    labels:
        label busy_eq_0 for EG: "service_count(server) == 0"
        label busy_eq_0 for ACD: "servers_busy() == 0"
    check: type=stutter_equivalence, run_length=100.0
endverification
```

## Related Work and ASM Frameworks

SimASM builds on the foundation of Abstract State Machines (ASM) introduced by
Gurevich [1, 2]. Several ASM implementations and tools have been developed:

- **ASM Workbench** [3]: Early implementation providing executable ASM specifications
- **ASMETA** [4]: ASM metamodel and toolset for interoperability
- **CoreASM** [5]: Extensible ASM execution engine with microkernel architecture

SimASM adapts from these earlier ASM implementations and applies ASM to discrete-event simulation, following Wagner's foundational work on ASM-based DES semantics [6].
The stutter equivalence verification is based on techniques from model checking [7].

### References

1. Gurevich, Y. (1993). Evolving Algebras: An Attempt to Discover Semantics.
   *Bulletin of the EATCS*, 43, 264-284.

2. Gurevich, Y. (2000). Sequential Abstract State Machines Capture Sequential
   Algorithms. *ACM Transactions on Computational Logic*, 1(1), 77-111.

3. Del Castillo, G. (1999). *The ASM Workbench: A Tool Environment for
   Computer-Aided Analysis and Validation of ASM Models*. PhD thesis, University
   of Paderborn.

4. Gargantini, A., Riccobene, E., & Scandurra, P. (2008). A Metamodel-based
   Language and a Simulation Engine for Abstract State Machines. *Journal of
   Universal Computer Science*, 14(12), 1949-1983.

5. Farahbod, R., Gervasi, V., & Glässer, U. (2009). Design and Specification of
   CoreASM: An Extensible ASM Execution Engine. *Fundamenta Informaticae*,
   77, 71-103.

6. Wagner, G. (2017). An abstract state machine semantics for discrete event simulation.
   2017 Winter Simulation Conference (WSC), 762-773.

7. Baier, C., & Katoen, J.-P. (2008). *Principles of Model Checking*. MIT Press.

## License

MIT License - See LICENSE file

## Links

- Repository: https://github.com/SimASM-Project/simasm-library
- Issues: https://github.com/SimASM-Project/simasm-library/issues
