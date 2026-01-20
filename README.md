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
pip install simasm[jupyter]

# From source (development)
git clone <repo-url>
cd simasm
pip install -e .[jupyter]
```

**Requirements:** Python 3.9+, lark>=1.1.0, pydantic>=2.0, numpy>=1.20,
matplotlib==3.9.2, scipy>=1.9

## Quick Start

### Option 1: Run a Jupyter Notebook
```bash
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
simasm/
├── notebooks/           # Interactive tutorials and examples
├── simasm/
│   ├── input/
│   │   ├── models/      # Pre-built .simasm model files
│   │   └── experiments/ # Experiment & verification specs
│   └── output/          # Generated results (JSON, CSV, PNG)
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

## License

MIT License - See LICENSE file

## Links

- Repository: https://github.com/SimASM-Project/simasm
- Issues: https://github.com/SimASM-Project/simasm/issues
