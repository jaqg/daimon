---
status: Active
type: SOP
subject: [Collab-IEM-NanoplasticZeolites]
---

# Manuscript Context — Collab-IEM-NanoplasticZeolites

## Target journal
Environmental Science & Technology (ACS). Impact factor ~11. Requires SI with all computational details, FAIR data statement, data availability statement. Word limit: 8000 words. Requires all software versions, URLs, and force field citations.

## Working title
Selective adsorption of nanoplastic polymer fragments in zeolite MFI: a DFT+GCMC study

## Key claims
- MFI zeolite adsorbs polyethylene fragments more strongly than polypropylene (ΔEads ~26 kJ/mol)
- PE:PP adsorption selectivity = 2.0 at 0.1 bar, 298 K
- Dispersion interactions dominate over electrostatics for non-polar polymer fragments
- Practical PE uptake capacity ~4.2 molecules/uc at 0.1 bar

## Computational methods (as used)
| Software | Version | Key parameters | Role |
|----------|---------|----------------|------|
| CASTEP | 23.1 | PBE-D3, 830 eV cutoff, counterpoise correction (BSSE 7–10 kJ/mol) | DFT adsorption energies |
| RASPA2 | 2.0.47 | GCMC, TraPPE-UA FF, 10^5 init + 10^5 production cycles, 298 K | Adsorption isotherms |
| Zeo++ | 0.3 | Voronoi tessellation, probe radius 1.82 Å | Pore characterisation |

## Key results
- BSSE-corrected PE adsorption energy (most stable site): −61.4 kJ/mol
- PE loading at 0.1 bar, 298 K: 4.2 ± 0.3 molecules/uc
- PP loading at 0.1 bar, 298 K: 2.1 ± 0.4 molecules/uc
- PE:PP selectivity = 2.0 ± 0.3

## Known weaknesses / anticipated reviewer concerns
- All-silica MFI model — real zeolites have Al substitution that changes channel electrostatics
- TraPPE-UA transferability to oxidised PP fragments (weathered nanoplastic) unvalidated
- Rigid zeolite framework — does not capture pore-window flexibility effects on diffusion

## Open questions
- What is the effect of Si/Al ratio on PE:PP selectivity?
