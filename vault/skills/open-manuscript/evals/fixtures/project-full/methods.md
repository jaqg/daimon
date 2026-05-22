---
status: Growing
type: SOP
subject: [Collab-IEM-NanoplasticZeolites]
---

# Methods — Collab-IEM-NanoplasticZeolites

## Computational setup

| Date | Software | Version | Key parameters | Notes |
|------|----------|---------|----------------|-------|
| 2026-01-10 | CASTEP | 23.1 | PBE-D3, 830 eV cutoff, BFGS geometry opt | Bulk zeolite geometry optimisation |
| 2026-01-15 | CASTEP | 23.1 | PBE-D3, 830 eV, 2×2×2 k-points | Single-point adsorption energies |
| 2026-02-05 | RASPA2 | 2.0.47 | GCMC, 10^5 init + 10^5 prod cycles, TraPPE-UA FF | Polymer fragment adsorption isotherms |
| 2026-02-20 | Zeo++ | 0.3 | Voronoi tessellation, probe radius 1.82 Å | Pore characterisation (LCD, PLD) |
| 2026-03-12 | CASTEP | 23.1 | PBE-D3, 830 eV, counterpoise correction | BSSE-corrected adsorption energies for Table 5 |
