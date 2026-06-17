# SimASM

**Abstract State Machine Framework for Discrete-Event Simulation**

SimASM is a programming language and verification framework that enables:

- Writing discrete-event simulation models using a clean DSL
- Supporting multiple DES formalisms (Event Graph, Activity Cycle Diagram, DEVS)
- Verifying behavioral equivalence between models via stutter equivalence
- Running experiments with statistics collection and automatic plotting

## Overview

SimASM adopts Abstract State Machines (ASM) as the semantic foundation for DES.
This enables precise translation of DES formalisms into a common formal language,
allowing rigorous verification of behavioral equivalence across formalisms.

**Key Concepts:**

- **Event Graph (EG)**: Event-based formalism using next-event time-advance algorithm
- **Activity Cycle Diagram (ACD)**: Activity-based formalism using three-phase scanning
- **DEVS**: Discrete Event System Specification formalism using abstract simulator algorithm
- **Stutter Equivalence**: Two models are equivalent if they produce the same
  sequence of observable state changes, regardless of internal steps
- **Complexity Analysis:** Semantic Model Complexity (SMC) metric computed statically

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

## Paper Reader's Guide

If you are reading the SIMULTECH 2026 or TOMACS paper (*Semantic Model Complexity
for Event Graph Discrete-Event Simulation Models*), this section maps paper sections
to the corresponding code and data in this repository.

### Paper Section → Repo Path

The TOMACS paper extends the SIMULTECH 2026 conference paper with additional
sections (Related Work, Weyuker axioms). Both section numbers are shown below.


| SIMULTECH     | TOMACS        | Topic                            | Repo Path                                                               |
| --------------- | --------------- | ---------------------------------- | ------------------------------------------------------------------------- |
| Fig. 1, §2.1 | Fig. 1, §3.1 | M/M/N Event Graph example        | `simasm/input/models/mm5_eg.simasm`                                     |
| §2.3         | §3.2         | ASM translation                  | `simasm/core/` (rules, states, terms)                                   |
| §3           | §4           | SMC metric definition            | `simasm/smc_complexity/api.py`                                          |
| §3           | §4           | HET cost assignment (Nowack)     | `simasm/smc_complexity/het_calculator.py`                               |
| §3           | §4           | Cycle detection and firing rates | `simasm/smc_complexity/cycle_finder.py`, `delay_resolver.py`            |
| —            | §5           | Weyuker axiom validation         | Proofs in paper; benchmark models as counterexamples in`simasm/models/` |
| §4           | §6           | Experimental design (51 models)  | `simasm/models/` (JSON), `simasm/models_simasm/` (.simasm)              |
| §5           | §7           | LOOCV results                    | `simasm/reproduce/loocv.py` → `simasm-reproduce loocv`                 |
| §6           | §8           | Warehouse case study             | `simasm/reproduce/warehouse.py` → `simasm-reproduce warehouse`         |
| —            | Appendix A    | Worked EG-to-ASM translation     | `simasm/models_simasm/mmn_5_eg.simasm`                                  |
| —            | Appendix B    | Reproducibility                  | `simasm/reproduce/cli.py` → `simasm-reproduce all`                     |

### Understanding the Three Model Directories

The benchmark models exist in three directories, each serving a different purpose:


| Directory               | Format    | Count | Purpose                                                                                                                       |
| ------------------------- | ----------- | ------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `simasm/models/`        | JSON      | 52    | Canonical Event Graph specifications (51 benchmark + 1 warehouse) — parsed by SMC computation and simulation engine          |
| `simasm/models_simasm/` | `.simasm` | 53    | ASM translations of the JSON models (51 benchmark + 1 warehouse + 1 M/M/N from Appendix A) — used for LOC and KC computation |
| `simasm/input/models/`  | `.simasm` | 14    | Hand-crafted models for interactive demos and verification (M/M/5, warehouse, in both EG and ACD)                             |

The **JSON files** define the Event Graph structure (vertices, edges, delays, conditions)
and are the primary input for simulation and SMC computation. The **.simasm files** in
`models_simasm/` are ASM translations of the same models, used to compute lines-of-code
(LOC) and Kolmogorov complexity (KC). The **input/models/** directory contains separate
hand-written models for the Quick Start tutorials and stutter equivalence verification.

### Benchmark Model Naming Convention

The 51 benchmark models follow a systematic naming scheme:

**Homogeneous (27 models):** `{topology}_{n}_eg.json`

- Topology: `tandem`, `fork_join`, `feedback`
- Sizes: n = 1, 2, 3, 4, 5, 7, 10, 15, 20 stations
- Fixed parameters: IAT mean = 1.25, IST mean = 1.0, service capacity = 5

**Heterogeneous (24 models):** `{topology}_{n}_{pattern}_{iat}_eg.json`

- Topology: `tandem`, `fork_join`, `feedback`
- Sizes: n = 5, 10
- IST pattern: `hetgrad` (graduated), `hetbottle` (bottleneck)
- IAT level: `iat10` (mean = 10.0), `iat30` (mean = 30.0)

**Warehouse (1 model):** `warehouse_eg.json` — 6-station industrial warehouse (out-of-sample)

## Exploring Individual Models

### Inspect a JSON Model

Each JSON file is a complete Event Graph specification. Here is `tandem_1_eg.json`
(truncated), showing the key sections that correspond to the formal definition
*S = (F, C, T, Γ, G)* from Section 3.1 of the paper:

```json
{
  "model_name": "tandem_1_eg",
  "parameters": {
    "service_capacity": { "type": "Nat", "value": 5 },
    "iat_mean": { "type": "Real", "value": 1.25 },
    "ist_mean": { "type": "Real", "value": 1.0 },
    "sim_end_time": { "type": "Real", "value": 10000.0 }
  },
  "state_variables": {
    "queue_count_1": { "type": "Nat", "initial": 0 },
    "server_count_1": { "type": "Nat", "initial": 0 }
  },
  "vertices": [
    {
      "name": "Arrive",
      "state_change": "load_id_counter := load_id_counter + 1; queue_count_1 := queue_count_1 + 1"
    },
    { "name": "Start_1", "state_change": "queue_count_1 := queue_count_1 - 1; server_count_1 := server_count_1 + 1" },
    { "name": "Finish_1", "state_change": "server_count_1 := server_count_1 - 1; departure_count := departure_count + 1" }
  ],
  "scheduling_edges": [
    { "from": "Arrive", "to": "Arrive", "delay": "interarrival_time", "condition": "true" },
    { "from": "Arrive", "to": "Start_1", "delay": 0, "condition": "server_count_1 < service_capacity" },
    { "from": "Start_1", "to": "Finish_1", "delay": "service_time_1", "condition": "true" },
    { "from": "Finish_1", "to": "Start_1", "delay": 0, "condition": "queue_count_1 > 0 and server_count_1 < service_capacity" }
  ],
  "cancelling_edges": [],
  "initial_events": [{ "event": "Arrive", "time": "interarrival_time" }],
  "stopping_condition": "sim_clocktime >= sim_end_time"
}
```

### Compute SMC for a Single Model

```python
from simasm.smc_complexity import compute_smc

result = compute_smc("simasm/models_simasm/tandem_5_eg.simasm",
                     "simasm/models/tandem_5_eg.json")
print(f"SMC = {result.smc:.1f}")
for v in result.vertex_details:
    print(f"  {v.name}: rate={v.rate:.3f}, deg={v.degree}, HET={v.het_cost}, contrib={v.contribution:.1f}")
```

### Compute All Four Metrics

```python
from simasm.smc_complexity import compute_smc
from simasm.reproduce.metrics import compute_cc, compute_loc, compute_kc

model = "tandem_5_eg"
smc = compute_smc(f"simasm/models_simasm/{model}.simasm",
                  f"simasm/models/{model}.json").smc
cc  = compute_cc(f"simasm/models/{model}.json")
loc = compute_loc(f"simasm/models_simasm/{model}.simasm")
kc  = compute_kc(f"simasm/models_simasm/{model}.simasm")

print(f"SMC={smc:.1f}  CC={cc}  LOC={loc}  KC={kc:.2f}")
```

### Run a Single Simulation

```python
from datetime import timedelta
from simasm.o2despy_eg import EventGraphModel

model = EventGraphModel.from_json("simasm/models/tandem_5_eg.json", seed=42)
model.run(duration=timedelta(hours=10000))
print(f"Departures: {model.departure_count}")
```

### Measure Runtime (30 Replications)

```python
from simasm.reproduce.runtime_measure import measure_runtime

stats = measure_runtime("simasm/models/tandem_5_eg.json", num_reps=30)
print(f"Mean={stats['runtime_mean']:.3f}s  Std={stats['runtime_std']:.3f}s")
```

## Reproducing Paper Results

SimASM includes a reproducibility module for the research paper.

### Experiment 1: 51-Model LOOCV Validation (Section 7)

```bash
simasm-reproduce loocv
```

Runs the full 51-model benchmark (~5 min). Measures simulation runtimes live
(30 replications each), computes SMC/CC/LOC/KC, and performs leave-one-out
cross-validation on three pools (27 homogeneous, 24 heterogeneous, 51 combined).

### Experiment 2: Warehouse Case Study (Section 8)

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

- **Q²**: SMC ≈ 0.95 on the combined 51-model pool (predictive R² from leave-one-out cross-validation)
- **Sign test**: SMC outpredicts CC/LOC/KC on 51/51 models (p < 0.0001)
- **Warehouse**: only SMC's 95% prediction interval contains the actual runtime

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

See [Benchmark Model Naming Convention](#benchmark-model-naming-convention) for the full naming scheme.

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
│   ├── models/              # 52 benchmark EG JSON specifications
│   ├── models_simasm/       # 53 benchmark SimASM translations
│   ├── smc_complexity/      # SMC v10 metric computation (Section 4)
│   ├── o2despy_eg/          # Event Graph simulation engine
│   ├── reproduce/           # Paper reproducibility CLI (Appendix B)
│   ├── converter/           # JSON-to-SimASM conversion
│   ├── core/                # ASM term/state/rule representation
│   ├── experimenter/        # Experiment & verification CLI
│   ├── parser/              # SimASM parser
│   ├── runtime/             # ASM execution engine
│   ├── simulation/          # Experiment runner & statistics
│   ├── verification/        # Stutter equivalence verification
│   ├── input/
│   │   ├── models/          # Hand-crafted .simasm models (M/M/5, warehouse)
│   │   └── experiments/     # Experiment & verification specs
│   └── output/              # Generated results (JSON, CSV, PNG)
├── pyproject.toml
└── README.md
```

## Notebooks Guide


| Notebook                                  | Description                                    | Paper Section                     | Order |
| ------------------------------------------- | ------------------------------------------------ | ----------------------------------- | ------- |
| `simasm_demo.ipynb`                       | Interactive intro using Jupyter magic commands | —                                | 1     |
| `simasm_python_api_demo.ipynb`            | Python API alternative to magics               | —                                | 1     |
| `eg_littles_law.ipynb`                    | Event Graph + Little's Law verification        | Section 3.1 (EG formalism)        | 2     |
| `acd_littles_law.ipynb`                   | ACD + Little's Law verification                | Section 3.1 (ACD formalism)       | 2     |
| `eg_to_asm_translation.ipynb`             | Formal EG→ASM translation algorithm           | Section 3.2, Appendix A           | 3     |
| `acd_to_asm_translation.ipynb`            | Formal ACD→ASM translation algorithm          | Section 3.2                       | 3     |
| `mm5_verification.ipynb`                  | Stutter equivalence verification (M/M/5)       | Section 3.2 (stutter equivalence) | 4     |
| `warehouse_verification.ipynb`            | Complex 6-station warehouse verification       | Section 8 (case study model)      | 5     |
| `warehouse_verification_w_analysis.ipynb` | Extended statistical analysis                  | Section 8                         | 5     |

## Input Files

### Models (`simasm/input/models/`)


| File                   | Description                                |
| ------------------------ | -------------------------------------------- |
| `mm5_eg.simasm`        | M/M/5 queue using Event Graph formalism    |
| `mm5_acd.simasm`       | M/M/5 queue using Activity Cycle Diagram   |
| `warehouse_eg.simasm`  | 6-station warehouse outbound process (EG)  |
| `warehouse_acd.simasm` | 6-station warehouse outbound process (ACD) |

### Experiments (`simasm/input/experiments/`)


| File                                     | Description                                |
| ------------------------------------------ | -------------------------------------------- |
| `littles_law_eg.simasm`                  | Little's Law verification (L = λW) for EG |
| `littles_law_acd.simasm`                 | Little's Law verification for ACD          |
| `mm5_verification.simasm`                | Stutter equivalence: EG vs ACD             |
| `warehouse_w_stutter_equivalence.simasm` | Warehouse model verification               |

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
