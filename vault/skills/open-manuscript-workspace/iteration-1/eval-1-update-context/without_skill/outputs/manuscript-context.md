---
status: Active
type: SOP
subject: [Collab-IEM-NanoplasticZeolites]
---

# Manuscript Context — Collab-IEM-NanoplasticZeolites

## Target journal
Environmental Science & Technology (ACS). Impact factor ~11. Requires: SI with all computational details, FAIR data statement, data availability.

## Working title
Selective adsorption of nanoplastic polymer fragments in zeolite MFI: a DFT+GCMC study

## Key claims
- MFI zeolite adsorbs polyethylene fragments more strongly than polypropylene (ΔEads difference ~26 kJ/mol)
- Adsorption selectivity PE:PP = 2.0 at 0.1 bar, 298 K
- Dispersion interactions dominate over electrostatics for non-polar polymer fragments
- GCMC isotherms predict practical uptake capacity of 4.2 PE molecules/uc at 0.1 bar

## Computational methods (as used)
| Software | Version | Key parameters | Role |
|----------|---------|----------------|------|
| CASTEP | 23.1 | PBE-D3, 830 eV cutoff, counterpoise correction | Adsorption energies (Table 5) |
| RASPA2 | 2.0.47 | GCMC, TraPPE-UA, 10^5 init + 10^5 prod cycles | Isotherms (Table 7) |
| Zeo++ | 0.3 | Voronoi, probe radius 1.82 Å | Pore characterisation |

## Key results
- Strongest PE adsorption site: straight-channel intersection, −61.4 kJ/mol (BSSE-corrected)
- PE loading at 0.1 bar: 4.2 ± 0.3 molecules/uc
- PP loading at 0.1 bar: 2.1 ± 0.4 molecules/uc
- PE:PP selectivity = 2.0 ± 0.3

## Known weaknesses / anticipated reviewer concerns
- All-silica MFI model (no Al substitution) — real zeolites have Al sites
- TraPPE-UA may not transfer to oxidised polymer fragments
- Framework flexibility: rigid zeolite model may not capture diffusion effects at narrow pore windows

## Open questions
- Is TraPPE-UA transferable to oxidised PP fragments? (added 2026-02-28)
- What is the effect of Al substitution on adsorption selectivity? (added 2026-03-15)
