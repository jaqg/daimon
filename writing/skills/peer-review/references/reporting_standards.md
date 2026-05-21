# Scientific Reporting Standards and Guidelines

Catalog of major reporting standards across scientific disciplines. When reviewing manuscripts, verify that authors followed the appropriate guidelines for their study type. Sections are organized by discipline; see also the journal-specific section at the end.

---

## Clinical Trials and Medical Research

### CONSORT (Consolidated Standards of Reporting Trials)
**Purpose:** Randomized controlled trials (RCTs)
**Key Requirements:**
- Trial design, participants, and interventions clearly described
- Primary and secondary outcomes specified
- Sample size calculation and statistical methods
- Participant flow (enrollment, allocation, follow-up, analysis)
- Baseline characteristics of participants
- Numbers analyzed in each group with confidence intervals
- Adverse events
- Trial registration number and protocol access

**Reference:** http://www.consort-statement.org/

### STROBE (Strengthening the Reporting of Observational Studies in Epidemiology)
**Purpose:** Observational studies (cohort, case-control, cross-sectional)
**Key Requirements:**
- Study design clearly stated
- Setting, eligibility criteria, and participant sources
- Variables clearly defined with data sources and measurement methods
- Bias assessment and sample size justification
- Statistical methods including handling of missing data
- Main results with confidence intervals
- Limitations discussed

**Reference:** https://www.strobe-statement.org/

### PRISMA (Preferred Reporting Items for Systematic Reviews and Meta-Analyses)
**Purpose:** Systematic reviews and meta-analyses
**Key Requirements:**
- Protocol registration
- Systematic search strategy across multiple databases
- Inclusion/exclusion criteria and study selection process
- Data extraction and quality assessment methods
- Statistical methods for meta-analysis
- Assessment of publication bias and heterogeneity
- PRISMA flow diagram

**Reference:** http://www.prisma-statement.org/

### SPIRIT, CARE, ARRIVE
- **SPIRIT:** Clinical trial protocols — administrative info, rationale, methods, ethics
- **CARE:** Case reports — patient info, clinical findings, timeline, outcomes, consent
- **ARRIVE:** Animal research — ethical statement, housing, animal details, procedures, blinding, sample size

---

## Genomics and Molecular Biology

### MIAME
**Purpose:** Microarray experiments
**Key Requirements:** Experimental design, array design, samples, hybridization, image acquisition, normalization, raw data availability with accession numbers

### MINSEQE
**Purpose:** High-throughput sequencing (RNA-seq, ChIP-seq, etc.)
**Key Requirements:** Experimental design, sample preparation, library protocol, sequencing platform, processing pipeline (alignment, quantification, normalization), QC metrics, raw data deposition (SRA/GEO/ENA)

### MIGS/MIMS
**Purpose:** Genome and metagenome sequencing
**Key Requirements:** Sample origin, sequencing methods/coverage, assembly methods/quality metrics, annotation, data deposition in INSDC databases

---

## Structural Biology

### PDB Deposition Requirements
**Purpose:** Macromolecular structure determination
**Key Requirements:**
- Atomic coordinates deposited before publication
- Structure factors (X-ray), restraints (NMR), or EM maps deposited
- Model quality validation metrics (R-factors, clashscore, Ramachandran)
- Experimental conditions (crystallization, sample preparation)
- Data collection and refinement statistics in manuscript

**Reference:** https://www.wwpdb.org/

---

## Proteomics and Mass Spectrometry

### MIAPE
**Purpose:** Proteomics experiments
**Key Requirements:** Sample processing, separation methods, MS parameters (instrument/acquisition), database search/validation parameters, quantification methods, data deposition (PRIDE, PeptideAtlas)

---

## Computational Chemistry and Materials Science

### DFT and Electronic Structure Calculations

No single mandatory standard exists, but best practices (recommended by journals including JACS, PCCP, J. Chem. Theory Comput.) require:

**Minimum required information:**
- Software name, version, and citation
- Exchange-correlation functional (including hybrid, range-separated, meta-GGA variant)
- Dispersion correction scheme (none, D3, D3(BJ), D3(BJ)+ABC, MBD, Tkatchenko-Scheffler)
- Basis set or plane-wave cutoff energy (e.g., 520 eV)
- Pseudopotentials or PAW datasets (type, version, citation)
- k-point mesh for periodic calculations (scheme, density, e.g., 3×3×1 Monkhorst-Pack)
- SCF convergence threshold (e.g., 10⁻⁸ eV or 10⁻⁸ hartree)
- Ionic relaxation convergence (force threshold, e.g., 0.01 eV/Å; energy threshold)
- Spin polarization treatment (spin-polarized? magnetic moments initialized how?)
- Hubbard U values if DFT+U applied

**Strongly recommended:**
- BSSE correction for cluster/molecular interaction calculations
- ZPE and thermal corrections when reporting ΔH, ΔG, or comparing to experiment
- Charge analysis method cited (Bader, Hirshfeld, NBO, QTAIM implementation)
- Benchmark validation against experiment or higher-level theory
- Cell size convergence test for adsorption calculations in periodic systems

**Data deposition:**
- **ioChem-BD** (ichem.cat) — recommended by RSC, Elsevier chemistry journals for DFT data
- **NOMAD** (nomad-lab.eu) — EU open-data repository for computational materials science
- **Materials Project** (materialsproject.org) — for periodic DFT data on inorganic materials
- **Zenodo / Figshare** — general-purpose for scripts, input/output files

### Molecular Dynamics Simulations

**Minimum required information:**
- Force field(s) with full citation (TraPPE, OPLS-AA, AMBER, CHARMM, ReaxFF, etc.)
- Partial charge derivation method (RESP, DDEC3/6, CM5, Mulliken)
- Cutoff radius and long-range electrostatic method (PME, Ewald, reaction field)
- Long-range dispersion correction applied (yes/no)
- Thermostat and barostat algorithms with coupling constants
- Ensemble (NVT, NPT, NVE) and conditions (T, P)
- Equilibration and production run lengths (time or steps)
- Statistical uncertainty (block averaging, autocorrelation time)
- Software name and version

### Grand Canonical Monte Carlo (GCMC)

**Minimum required information:**
- Force field with full citation
- Partial charges: method used
- Cutoff radius (Å) for LJ and Coulomb interactions
- Chemical potential ↔ pressure conversion method (equation of state: PREOS, SRK, ideal gas; state conditions)
- Temperature and pressure range
- Number of MC cycles (equilibration vs. production)
- Move types and relative probabilities (insertion, deletion, displacement, rotation)
- Statistical uncertainty (standard deviation over independent runs or block averages)
- Software: RASPA, CASSANDRA, MUSIC, TOWHEE, etc.

### Crystal Structure Reporting (CSD / CCDC)
**Purpose:** Small-molecule X-ray crystallography
**Key Requirements:**
- CSD deposition number (CCDC) before publication
- R-factor, space group, unit cell parameters
- ORTEP diagram in supplementary
- Bond lengths/angles for key structural features

**Reference:** https://www.ccdc.cam.ac.uk/

---

## Chemistry — General and Synthetic

### MIRIBEL (Minimum Information Reporting in Bio-Nano Experimental Literature)
**Purpose:** Nanomaterial characterization
**Key Requirements:** Composition/structure, size/shape/morphology characterization, surface chemistry/functionalization, purity/stability, experimental conditions, characterization methods

### New Compound Characterization (JACS/Org. Lett. standard)
For any newly synthesized compound:
- Full spectral data: ¹H NMR, ¹³C NMR (with multiplicities, coupling constants, integration)
- HRMS (high-resolution mass spectrometry, exact mass)
- Melting point for solids
- Optical rotation for chiral compounds
- IR for key functional groups (optional if NMR+MS complete)
- Elemental analysis or HRMS for formula confirmation

---

## Machine Learning for Science

No universal standard exists, but emerging best practices (NeurIPS reproducibility checklist, JMLR, Nature Machine Intelligence guidelines):

**Minimum required information:**
- Dataset description: source, size, train/val/test split ratios, preprocessing steps
- Model architecture: layer types, dimensions, activation functions, parameter count
- Training procedure: optimizer, learning rate schedule, batch size, epochs, hardware
- Hyperparameter selection method (grid search, random search, Bayesian, fixed)
- Evaluation metric(s) and justification
- Multiple random seeds with mean ± std reported
- Baseline comparisons with identical evaluation conditions
- Ablation studies for key architectural or training choices

**Strongly recommended:**
- Code and model checkpoints deposited (GitHub, HuggingFace, Zenodo)
- Confidence intervals or standard deviations for all metrics
- Statistical significance test for improvements over baselines (t-test, bootstrap)
- Computational cost reported (GPU-hours, wall time, hardware specs)

---

## Journal-Specific Standards

### Nature / Nature Chemistry / Nature Communications

**Format and scope:**
- Letter/Article distinction: Letters ≤ 3000 words main text; Articles longer
- Significance to broad readership required — narrow specialist contributions rarely accepted
- Methods section in supplementary (for Letters); as separate section for Articles
- Extended Data figures (up to 10 full-page figures) for supporting data

**Mandatory at submission:**
- **Reporting Summary** (nature.com/authors/policies/reporting.html) — checklist covering: sample sizes, replication, randomization, blinding, statistics reporting, data availability. Must be completed before review.
- **Source Data** for all main figures (raw data underlying all panels) — mandatory for Nature/Nature Chemistry; strongly encouraged for Nature Communications
- Life Sciences Reporting Summary for biological studies
- Data availability statement with repository accession numbers

**Key review criteria:**
- Broadly significant advance (not incremental)
- Novelty in conceptual understanding, not just new examples
- Technical rigor with appropriate controls
- Does not just repeat known results in a new system

### JACS (Journal of the American Chemical Society)

**Format:**
- Letters vs. Articles — Letters ≤ 4 printed pages
- All new compounds: full characterization (see compound characterization section above)
- Supporting Information required for full experimental/computational details

**Key review criteria:**
- Significance to broad chemical community (not just synthetic novelty)
- Mechanistic insight strongly valued for reaction papers
- For computational papers: benchmarking against experiment or accurate theory required
- Functional choice must be justified for property calculations
- DFT data ideally deposited in ioChem-BD or NOMAD
- For materials: link between structure and property must be demonstrated

**Mandatory disclosures:**
- Conflict of interest
- Data availability

### Angewandte Chemie / ACIEE

**Key requirements:**
- Communications ≤ 5 printed pages; Articles longer
- Graphical abstract mandatory
- Broad significance across chemistry
- Supporting Information for all experimental details

### PCCP (Physical Chemistry Chemical Physics — RSC)

**Computational papers:**
- DFT data deposition in ioChem-BD recommended
- Full computational details in supplementary
- Convergence tests expected (k-points, cutoff, cell size for periodic)
- All energies referenced clearly (adsorption relative to what? ZPE included?)

### J. Chem. Theory Comput. (JCTC)

**Computational benchmark papers:**
- Reference values must be high-accuracy (CCSD(T)/CBS or experimental)
- Error metrics: MAE, RMSE, MAX reported per method
- Test set described with diversity and coverage
- Method transferability discussed

### NeurIPS / ICLR / ICML (ML conferences)

**Reproducibility checklist (NeurIPS):**
- Claims: all claims supported by evidence
- Theoretical: all theorems with proofs; assumptions stated
- Experiments: error bars from multiple runs; compute resources stated; code submitted
- Dataset: license, intended use, maintenance plan if new dataset

**Review criteria:**
- Technical correctness
- Significance and novelty of contribution
- Experimental validation: ablations, baselines, fair comparison
- Clarity and reproducibility
- Limitations section

---

## General Principles Across All Guidelines

### Common Requirements
1. **Transparency:** All methods, materials, and analyses fully described
2. **Reproducibility:** Sufficient detail for independent replication
3. **Data Availability:** Raw data and analysis code shared or deposited
4. **Registration:** Studies pre-registered where applicable (clinical, some observational)
5. **Ethics:** Appropriate approvals and consent documented
6. **Conflicts of Interest:** Disclosed for all authors
7. **Statistical Rigor:** Methods appropriate and fully described
8. **Completeness:** All outcomes reported, including negative results

### Red Flags for Non-Compliance
- Methods section lacks critical details (software version, parameters, thresholds)
- No data availability statement or vague "available upon request"
- No repository accession numbers for omics/structural data
- No deposition number for crystal structures or DFT datasets
- No trial registration for clinical studies
- Sample size not justified
- Statistical methods inadequately described
- Missing mandatory checklists (Reporting Summary for Nature journals)
- Selective reporting of outcomes

---

## How to Use This Reference

1. Identify study type and discipline
2. Find the relevant reporting guideline(s)
3. Check if authors mention following the guideline
4. Verify that key requirements are addressed
5. Note any missing elements in your review
6. Suggest the appropriate guideline if not mentioned

Many journals require authors to complete reporting checklists at submission. Reviewers should verify compliance even if a checklist was submitted.
