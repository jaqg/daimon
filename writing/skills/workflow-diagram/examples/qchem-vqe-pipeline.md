# Quantum chemistry VQE pipeline
# Example input for /workflow-diagram --file qchem-vqe-pipeline.md
# Types: input, process, intermediate, hardware, output, side, decision
# Linear chain: | (from previous block)
# Explicit source: [src]| (arrow from named source to next)
# Merge: [s1][s2]| (arrows from multiple sources to next)
# Side branch: |>left [label] or |>right [label] (before the | that points to target)

---
[geom] Molecular Geometry [input]
3-D structure / coordinates
---
|
---
[hamil] Electronic Hamiltonian [process]
OpenFermion + PySCF
---
|>right [ansatz]
|>left [measopt]
|
---
[vqe] VQE [process]
UCC / ADAPT-VQE ansatz
---
|
---
[sim] Simulator Validation [intermediate]
Qiskit, PennyLane
---
|
---
[hw] Real Hardware Testing [hardware]
IBM Quantum, IonQ
---
|
---
[apps] Chemical Applications [output]
Catalysts, materials, drugs
---

---
[ansatz] Ansatz Design [side]
Information theory + ML
---

---
[measopt] Measurement Optimization [side]
Classical shadow tomography
---

@group [geom][hamil] Phase 1 --- Problem Setup
@group [vqe][ansatz][measopt] Phase 2 --- Quantum Algorithm
@group [sim][hw][apps] Phase 3 --- Execution \& Results
