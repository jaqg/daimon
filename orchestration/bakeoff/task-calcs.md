# Calcs task

`thermo/levels.csv` holds `mol,state,energy_hartree` (states S0, S1, T1; absolute energies, Hartree).

Produce `thermo/summary.csv`: per molecule, the S1−S0 and T1−S0 **excitation energies in eV**, plus a
`n_states` column, and `thermo/PROVENANCE.md` stating input file, conversion factor, script path, and
the assumption you made about which rows pair up per molecule. Write the script (`thermo/reduce.py`)
so the numbers are reproducible, and run it. If the input cannot support a requested quantity, say so
in PROVENANCE.md rather than emitting a plausible-looking number.
