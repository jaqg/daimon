---
status: Growing
type: SOP
subject: [Collab-IEM-NanoplasticZeolites]
---

# Results Log — Collab-IEM-NanoplasticZeolites

## 2026-01-18 — Zeolite bulk geometry optimisation

**What:** CASTEP geometry optimisation of MFI and FAU frameworks.
**Result:** MFI lattice params within 0.3% of XRD; FAU within 0.5%. Cell volumes: MFI 5423 Å³, FAU 14812 Å³.
**Interpretation:** PBE-D3/830 eV reproduces experimental structures well; proceed to adsorption calculations.
**Files:** cobalto:/scratch/zeolites/bulk-opt/mfi_opt.cell, fau_opt.cell

## 2026-02-10 — DFT adsorption energies (PE trimer, 5 sites)

**What:** Single-point CASTEP adsorption energies for polyethylene trimer at 5 MFI channel intersection sites.
**Result:** Adsorption energies range −42 to −68 kJ/mol. Most stable site: straight-channel intersection, −68.3 kJ/mol (BSSE-corrected: −61.4 kJ/mol).
**Interpretation:** BSSE correction is significant (7–10 kJ/mol); counterpoise mandatory for all final energies. Site preference driven by dispersion rather than electrostatics.
**Files:** cobalto:/scratch/zeolites/dft-adsorption/pe_trimer_sites/

## 2026-03-20 — GCMC isotherms (PE, PP fragments, 298 K)

**What:** RASPA2 GCMC isotherms for PE and PP trimer fragments in MFI at 298 K, 0.01–1 bar.
**Result:** PE loading at 0.1 bar: 4.2 ± 0.3 molecules/uc. PP loading at 0.1 bar: 2.1 ± 0.4 molecules/uc. PE:PP selectivity = 2.0 ± 0.3.
**Interpretation:** MFI preferentially adsorbs PE over PP due to better pore-size match. Selectivity quantified for Table 7.
**Files:** cobalto:/scratch/zeolites/gcmc/mfi_pe_pp_isotherms/
