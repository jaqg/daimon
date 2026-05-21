# Common Methodological and Statistical Issues in Scientific Manuscripts

Catalog of frequent issues encountered during peer review, organized by category. Use as reference to identify potential problems and provide constructive feedback. Sections 1–22 cover general scientific issues; sections 23–25 cover computational chemistry; sections 26–27 cover editorial compliance; section 28 covers novelty assessment.

---

## Statistical Issues

### 1. P-Value Misuse and Misinterpretation

**Common Problems:**
- P-hacking (selective reporting of significant results)
- Multiple testing without correction (familywise error rate inflation)
- Interpreting non-significance as proof of no effect
- Focusing exclusively on p-values without effect sizes
- Dichotomizing continuous p-values at arbitrary thresholds (p=0.049 vs p=0.051)
- Confusing statistical significance with biological/clinical significance

**How to Identify:**
- Suspiciously high proportion of p-values just below 0.05
- Many tests performed but no correction mentioned
- Statements like "no difference was found" from non-significant results
- No effect sizes or confidence intervals reported

**What to Recommend:**
- Report effect sizes with confidence intervals
- Apply appropriate multiple testing corrections (Bonferroni, FDR, Holm-Bonferroni)
- Interpret non-significance cautiously (lack of evidence ≠ evidence of lack)
- Consider equivalence testing for "no difference" claims

### 2. Inappropriate Statistical Tests

**Common Problems:**
- Using parametric tests when assumptions are violated (non-normal data, unequal variances)
- Analyzing paired data with unpaired tests
- Using t-tests for multiple groups instead of ANOVA with post-hoc tests
- Treating ordinal data as continuous
- Ignoring repeated measures structure

**What to Recommend:**
- Check assumptions explicitly (normality tests, Q-Q plots)
- Use non-parametric alternatives when appropriate
- Apply proper corrections for multiple comparisons after ANOVA
- Use mixed-effects models for repeated measures

### 3. Sample Size and Power Issues

**Common Problems:**
- No sample size justification or power calculation
- Underpowered studies claiming "no effect"
- Post-hoc power calculations (which are uninformative)
- Stopping rules not pre-specified

**What to Recommend:**
- Conduct a priori power analysis based on expected effect size
- Report achieved power or precision (confidence interval width)
- Acknowledge when studies are underpowered

### 4. Missing Data Problems

**Common Problems:**
- Complete case analysis without justification (listwise deletion)
- Not reporting extent or pattern of missingness
- Assuming data are missing completely at random (MCAR) without testing
- Inappropriate imputation methods

**What to Recommend:**
- Report extent and patterns of missingness
- Use appropriate methods (multiple imputation, maximum likelihood)
- Perform sensitivity analyses

### 5. Circular Analysis and Double-Dipping

**Common Problems:**
- Using the same data for selection and inference
- Post-hoc subgroup analyses presented as planned
- HARKing (Hypothesizing After Results are Known)

**What to Recommend:**
- Use independent datasets for selection and testing
- Pre-register analyses and hypotheses
- Clearly distinguish confirmatory vs. exploratory analyses

### 6. Pseudoreplication

**Common Problems:**
- Technical replicates treated as biological replicates
- Multiple measurements from same subject treated as independent
- Clustered data analyzed without accounting for clustering

**What to Recommend:**
- Define n as biological replicates
- Use mixed-effects models for nested or clustered data
- Average technical replicates before analysis

---

## Experimental Design Issues

### 7. Lack of Appropriate Controls

**Common Problems:**
- Missing negative controls
- Missing positive controls for validation
- No vehicle controls for drug studies
- No batch controls

**What to Recommend:**
- Include negative controls to assess specificity
- Include positive controls to validate methods
- Include batch controls for cross-batch comparisons

### 8. Confounding Variables

**Common Problems:**
- Systematic differences between groups besides intervention
- Batch effects not controlled or corrected
- No randomization of sample order
- No mention of blinding

**What to Recommend:**
- Randomize experimental units to conditions
- Block on known confounders
- Use blinding to minimize bias

### 9. Insufficient Replication

**Common Problems:**
- Single experiment without replication
- Technical replicates mistaken for biological replication
- No independent validation of key findings
- Cherry-picking representative examples

**What to Recommend:**
- Perform independent biological replicates (typically ≥3)
- Validate key findings in independent cohorts
- Report all replicates, not just representative examples

---

## Reproducibility Issues

### 10. Insufficient Methodological Detail

**Common Problems:**
- Methods not described in sufficient detail for replication
- Key reagents not specified (vendor, catalog number)
- Software versions and parameters not reported
- Vague descriptions ("standard protocols were used")

**What to Recommend:**
- Provide detailed protocols or cite specific protocols
- Include reagent vendors, catalog numbers, lot numbers
- Report software versions and all parameters
- Make protocols available (protocols.io, supplementary materials)

### 11. Data and Code Availability

**Common Problems:**
- No data availability statement
- "Data available upon request" (often unfulfilled)
- No code provided for computational analyses
- No clear documentation

**What to Recommend:**
- Deposit raw data in appropriate repositories (GEO, SRA, Dryad, Zenodo)
- Share analysis code on GitHub or similar
- Use DOIs for permanent data citation

### 12. Lack of Method Validation

**Common Problems:**
- New methods not compared to gold standard
- Assays not validated for specificity, sensitivity, linearity
- No spike-in controls

**What to Recommend:**
- Validate new methods against established approaches
- Show specificity controls
- Report limits of detection and quantification

---

## Interpretation Issues

### 13. Overstatement of Results

**Common Problems:**
- Causal language for correlational data
- Mechanistic claims without mechanistic evidence
- Extrapolating beyond data (species, conditions, populations)
- Claiming "first to show" without thorough literature review

**What to Recommend:**
- Use appropriate language ("associated with" vs. "caused by")
- Distinguish correlation from causation
- Provide thorough literature context

### 14. Cherry-Picking and Selective Reporting

**Common Problems:**
- Reporting only significant results
- Showing "representative" images that may not be typical
- Excluding outliers without justification
- Not reporting negative or contradictory findings

**What to Recommend:**
- Report all planned analyses regardless of outcome
- Pre-specify outlier exclusion criteria
- Include negative results

### 15. Ignoring Alternative Explanations

**Common Problems:**
- Preferred explanation presented without considering alternatives
- Contradictory evidence dismissed without discussion
- Limitations section minimal or absent

**What to Recommend:**
- Discuss alternative explanations
- Address contradictory findings from literature
- Acknowledge and discuss limitations thoroughly

---

## Figure and Data Presentation Issues

### 16. Inappropriate Data Visualization

**Common Problems:**
- Bar graphs for continuous data (hiding distributions)
- No error bars or error bars not defined
- Truncated y-axes exaggerating differences
- Colors not colorblind-friendly

**What to Recommend:**
- Show individual data points with scatter/box/violin plots
- Always define error bars (SD, SEM, 95% CI)
- Use colorblind-friendly palettes (viridis, colorbrewer)
- Include sample sizes in figure legends

### 17. Image Manipulation Concerns

**Common Problems:**
- Excessive contrast/brightness adjustment
- Spliced gels or images without indication
- Duplicated images or panels

**What to Recommend:**
- Apply adjustments uniformly across images
- Indicate spliced gels with dividing lines
- Show full, uncropped images in supplementary materials

---

## Study Design Issues

### 18. Poorly Defined Hypotheses and Outcomes

**Common Problems:**
- No clear hypothesis stated
- Primary outcome not specified
- Multiple outcomes without correction
- Exploratory study presented as confirmatory

**What to Recommend:**
- State clear, testable hypotheses
- Designate primary and secondary outcomes a priori
- Apply appropriate corrections for multiple outcomes

### 19. Baseline Imbalance and Selection Bias

**Common Problems:**
- Groups differ at baseline
- Selection criteria applied differentially
- Survivorship bias

**What to Recommend:**
- Report baseline characteristics
- Use randomization to ensure balance
- Consider propensity score matching for observational data

### 20. Temporal and Batch Effects

**Common Problems:**
- Samples processed in batches by condition
- Temporal trends not accounted for
- Different operators for different groups

**What to Recommend:**
- Randomize samples across batches/time
- Include batch as covariate in analysis
- Balance operators across conditions

---

## Reporting Issues

### 21. Incomplete Statistical Reporting

**Common Problems:**
- Test statistics not reported
- Exact p-values replaced with inequalities (p<0.05)
- No confidence intervals or effect sizes
- Sample sizes not reported per group

**What to Recommend:**
- Report complete test statistics (t, F, χ² with df)
- Report exact p-values (except p<0.001)
- Include 95% confidence intervals and effect sizes

### 22. Methods-Results Mismatch

**Common Problems:**
- Methods describe analyses not performed
- Results include analyses not described in methods
- Different sample sizes in methods vs. results

**What to Recommend:**
- Ensure complete concordance between methods and results
- Verify all numbers are consistent

---

## Computational Chemistry Specific Issues

### 23. DFT and Electronic Structure Calculation Gaps

**Common Problems:**
- SCF convergence criterion not stated (reproducibility requires exact threshold)
- K-point sampling not described for periodic systems (mesh density, scheme)
- Plane-wave cutoff or basis set not specified
- Exchange-correlation functional choice not justified (GGA vs hybrid vs meta-GGA)
- Dispersion/van der Waals correction scheme not identified (D3, D3BJ, D3(BJ)+ABC, MBD, TS)
- Geometry relaxation convergence (force/energy thresholds) not reported
- Software package version and pseudopotential/PAW dataset not stated
- Spin state or magnetic ordering not specified where relevant
- Hubbard U parameters (DFT+U) applied without justification or citation
- Solvation model parameters not stated for solution-phase calculations

**How to Identify:**
- Methods section names software (VASP, CP2K, Gaussian, ORCA) without version
- "DFT calculations were performed" with no functional or cutoff mentioned
- No mention of k-point mesh for crystalline/periodic systems
- Adsorption energies reported with no mention of dispersion correction

**What to Recommend:**
- State: functional, dispersion scheme, cutoff/basis set, k-point mesh (e.g., 3×3×1 Monkhorst-Pack), SCF convergence (e.g., 10⁻⁸ eV), ionic relaxation convergence (e.g., forces < 0.01 eV/Å), software name and version, pseudopotentials used
- Justify functional choice, especially if non-standard
- Benchmark against experiment or higher-level theory for at least one system

### 24. Molecular Dynamics and Monte Carlo Simulation Gaps

**Common Problems:**
- Force field parameters not cited (LJ ε/σ values, source FF)
- Partial charge derivation method not stated (RESP, DDEC, Mulliken)
- Cutoff radius and long-range correction scheme not reported
- Equilibration vs. production run lengths not distinguished
- Statistical uncertainty (block averaging, autocorrelation) not reported
- Ensemble (NVT/NPT/μVT) not specified
- For GCMC: fugacity ↔ pressure conversion method not stated
- Periodic boundary conditions and cell size convergence test absent

**How to Identify:**
- "MD simulations were performed" with no force field citation
- Only mean values reported, no standard deviations or confidence intervals
- Number of MC cycles given without distinguishing equilibration
- Grand canonical simulations with no description of chemical potential calculation

**What to Recommend:**
- Cite force field fully (TraPPE, UFF, DREIDING, etc.)
- Report: ensemble, temperature, pressure, cutoff, LRC scheme, N steps (equilibration + production)
- Report statistical uncertainty via block averaging or error propagation
- For GCMC: specify fugacity calculation method (PREOS, Peng-Robinson, ideal gas limit)

### 25. Computational Results Interpretation Issues

**Common Problems:**
- Adsorption/binding energies compared across different methods without justification
- Counterpoise correction (BSSE) not applied or discussed for cluster calculations
- Zero-point energy and thermal corrections omitted for thermochemical comparisons
- Charge analysis method not stated (Bader, Mulliken, NBO, Hirshfeld)
- Orbital analysis (HOMO/LUMO, NBO, QTAIM) used without citing implementation
- Claims of "excellent agreement with experiment" without quantitative error metric
- Computed properties extrapolated beyond validated applicability range

**What to Recommend:**
- Apply and report BSSE correction for intermolecular cluster calculations
- Include ZPE + thermal corrections when comparing to experimental ΔH or ΔG
- State charge analysis method and cite implementation
- Provide quantitative error metrics (MAE, RMSE) when comparing to reference data
- Discuss method limitations explicitly

### 26. TD-DFT and Excited-State Calculation Gaps

**Common Problems:**
- Functional not validated for excited states — standard GGAs/hybrids fail for charge-transfer (CT) states; range-separated hybrids (CAM-B3LYP, ωB97X-D, LC-ωPBE) required for CT/Rydberg
- Basis set lacks diffuse functions for Rydberg or CT states (6-31G* insufficient; aug-cc-pVDZ or 6-311++G** recommended)
- Too few excited states computed — spectrum coverage incomplete, especially if multiple chromophores or near-degenerate states
- Solvent effects absent or treated only with implicit PCM when specific solute-solvent H-bonds dominate
- Ground-state geometry not confirmed to be the correct minimum before vertical excitation
- Vibronic structure ignored when comparing to room-temperature experimental spectra (FC, AH, VH, or VG model not specified)
- ECD rotational strengths reported in length gauge only — origin-dependent; velocity gauge (R2) should accompany or replace
- Absolute configuration not stated or assumed without optical rotation / VCD corroboration
- Sign pattern of Cotton effects not discussed relative to known chromophore rules
- Franck-Condon factors not validated against experimental band shape

**How to Identify:**
- "TD-DFT calculations were performed using B3LYP" with no validation for charge-transfer character
- ECD spectrum shows only stick spectrum with no broadening or vibronic structure
- Rotational strengths reported without specifying gauge (length vs velocity)
- "Good agreement with experiment" claimed but ΔE errors not quantified

**What to Recommend:**
- For CT/push-pull chromophores: use and benchmark range-separated functional; compare λ_max error vs experiment
- Add diffuse functions (minimum aug-cc-pVDZ or 6-311+G*)
- Specify vibronic model if lineshape is compared to experiment (FC, AH, VH, or VG) and cite software (FCclasses3, ORCA ESD, Gaussian FC)
- Report both length and velocity rotational strengths; prefer velocity gauge (origin-independent)
- Confirm absolute configuration from optical rotation sign before interpreting ECD

### 27. Machine Learning Interatomic Potential (MLIP) Gaps

**Common Problems:**
- Training set coverage not described — chemical space, number of structures, DFT level of reference
- No out-of-distribution (OOD) validation — transferability to configurations not seen during training untested
- Energy and force errors not separately reported (RMSE in meV/atom for energies; meV/Å for forces)
- Physical symmetry invariances (rotation, translation, permutation) not stated or verified
- No MD stability test — mean energy drift, temperature conservation, no unphysical structures generated
- Uncertainty quantification absent (no committee disagreement, deep ensembles, or conformal prediction)
- Comparison to existing state-of-the-art MLIPs (MACE, NequIP, CHGNet, SevenNet, etc.) missing
- Reactive or bond-breaking chemistry claimed without validating dissociation curves
- DFT reference level inconsistent between training and benchmark data

**How to Identify:**
- Training set described only by "N structures from DFT" with no composition/diversity analysis
- Energy errors reported only in absolute kcal/mol with no per-atom normalization
- "Stable MD trajectories" claimed without showing energy conservation or pair distribution functions
- Accuracy claimed vs experiment, not vs reference DFT level

**What to Recommend:**
- Report training set: composition distribution, coverage of relevant configurations (minima, TS, distorted geometries), DFT level and software
- Report per-atom energy RMSE and force RMSE on held-out test set
- Test on OOD configurations (temperature extrapolation, chemically distinct structures)
- Run NVE MD and plot energy drift over ≥1 ns; report g(r) for key atom pairs
- Compare to at least one published MLIP on identical test set where possible

---

## Editorial Compliance Checks

### 26. Missing Mandatory Disclosures

**Common Problems:**
- No conflict of interest statement (required by virtually all journals)
- No ethics statement for studies involving humans, animals, or sensitive data
- No data availability statement (increasingly mandatory)
- No funding acknowledgment
- Author contributions not stated (CRediT taxonomy increasingly required)
- Trial/study registration number absent for clinical/interventional work

**How to Identify:**
- Scan end-of-manuscript sections; these are typically required even if "none to declare"
- Clinical/intervention studies without ClinicalTrials.gov or similar number

**What to Recommend:**
- Add conflict of interest statement (explicit "none to declare" is acceptable)
- Add ethics statement citing institutional approval or justifying exemption
- Add data availability statement with repository URLs or explicit "available upon request" justification
- Add funding statement; "no specific funding" is acceptable
- Add author contributions (CRediT roles: conceptualization, methodology, software, validation, etc.)

### 27. Reference and Citation Integrity

**Common Problems:**
- Citations present in abstract (most journals prohibit this)
- Uncited references in reference list (present but never cited in text)
- Orphan citations (cited in text but absent from reference list)
- References without DOI or URL where findable
- Over-reliance on recent self-citations without justification
- Citing retracted papers without acknowledgment of retraction
- Reference style inconsistency within manuscript

**How to Identify:**
- Check abstract for any citation markers
- Cross-check every [n] in text against reference list
- Look for ≥20% self-citations in reference list

**What to Recommend:**
- Remove citations from abstract unless journal explicitly allows them
- Reconcile orphan and uncited references
- Add DOIs to all references where available
- Flag self-citation rate if unusually high; ensure cited prior work is genuinely relevant
- If citing a retracted paper: add retraction notice or remove

---

## Novelty and Contribution Assessment

### 28. Novelty, Positioning, and Contribution Gaps

*Note: AI assessment of novelty is inherently limited — flag these issues at severity "minor" and recommend the authors verify against their own literature search.*

**Common Problems:**
- Contribution not clearly distinguished from prior work in introduction
- Missing citation to a directly competing or foundational paper that should be addressed
- Incremental advance presented as breakthrough without quantitative comparison to state-of-the-art
- Hypothetical expected experiments implied by the claims are absent from the paper (MARG "experiment gap" heuristic: for each major claim, ask "what experiment would you expect to see?" — if it's missing, flag it)
- Limitations of novelty not acknowledged (e.g., same method, new substrate, no new insight)
- Title or abstract claims broader scope than results support

**How to Identify:**
- Introduction section describes a gap, then results section fills it — check whether the gap description is accurate given current literature
- Major quantitative claim ("outperforms X") without a direct comparison table/figure
- Discussion that doesn't connect back to the stated gap in the introduction

**What to Recommend:**
- Add an explicit "compared to [prior work], this paper demonstrates [quantitative difference]" statement
- Cite the most relevant prior work even if it weakens the novelty claim; address the comparison
- For claims of "first to show": add footnote acknowledging literature search scope and date
- For missing expected experiments: either add the experiment or explicitly scope the claim to match available data

---

## How to Use This Reference

When reviewing manuscripts:
1. Read through methods and results systematically
2. Check for common issues in each category relevant to the discipline
3. Note specific problems with evidence from the text
4. Provide constructive suggestions for improvement
5. Distinguish major issues (affect validity) from minor issues (affect clarity)
6. Prioritize reproducibility and transparency
7. For computational chemistry papers: apply sections 23–25 in addition to general checks

This is not an exhaustive list but covers the most frequently encountered issues. Always consider the specific context and discipline when evaluating potential problems.
