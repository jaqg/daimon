---
status: Active
type: SOP
subject: [Collab-IEM-NanoplasticZeolites]
---

# Manuscript Context — Collab-IEM-NanoplasticZeolites

## Target journal
Environmental Science & Technology (ACS). Impact factor ~11. Requires SI with computational details, FAIR data statement, data availability statement.

## Working title
Selective adsorption of nanoplastic polymer fragments in zeolite MFI: a DFT+GCMC study

## Key claims
- MFI zeolite adsorbs polyethylene fragments more strongly than polypropylene by ~26 kJ/mol
- PE:PP adsorption selectivity = 2.0 at 0.1 bar, 298 K
- Dispersion interactions dominate over electrostatics for non-polar polymer fragments in MFI channels
- Practical PE uptake capacity ~4.2 molecules/uc at 0.1 bar

## Computational methods (as used)
| Software | Version | Key parameters | Role |
|----------|---------|----------------|------|
| CASTEP | 23.1 | PBE-D3, 830 eV cutoff, counterpoise correction | Adsorption energies (Table 5) |
| RASPA2 | 2.0.47 | GCMC, TraPPE-UA FF, 10^5 init + 10^5 prod cycles | Polymer fragment isotherms (Table 7) |
| Zeo++ | 0.3 | Voronoi tessellation, probe radius 1.82 Å | Pore characterisation (LCD, PLD) |

## Key results
- Bulk MFI geometry optimised: cell volume 5423 Å³, within 0.3% of XRD
- Most stable PE trimer adsorption site: straight-channel intersection, −61.4 kJ/mol (BSSE-corrected; BSSE = 7–10 kJ/mol)
- PE loading at 0.1 bar: 4.2 ± 0.3 molecules/uc; PP loading: 2.1 ± 0.4 molecules/uc
- PE:PP selectivity = 2.0 ± 0.3 at 0.1 bar, 298 K

## Known weaknesses / anticipated reviewer concerns
- All-silica MFI model — real zeolites have Al substitution sites that alter channel electrostatics
- TraPPE-UA force field may not transfer to oxidised PP fragments from weathered nanoplastic

## Open questions
### Is TraPPE-UA transferable to oxidised PP fragments? (added 2026-02-28)
TraPPE-UA was parameterised for alkanes. PP fragments in weathered nanoplastic may carry carbonyl/hydroxyl groups. No literature precedent for TraPPE-UA on oxidised polyolefin in zeolite pores.

### What is the effect of Al substitution on adsorption selectivity? (added 2026-03-15)
All DFT and GCMC so far use all-silica MFI. Reviewer will likely ask whether Al sites change selectivity.
