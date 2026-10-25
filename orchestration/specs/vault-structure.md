# Spec: bring vault projects up to the role contract's expected layout

**Part:** `structure` · **Owner:** José · **Consumers:** `/brain`, `/triage`, `/merge-status`, `worktree.sh`
**Repo:** `$AAD_IA/daimon` (the vault itself is NOT a worktree target — see §5)

## 1. Problem the role contract has (measured 2026-10-25)

`agents/brain.md` and `merge-status.py` assume every project folder contains `plans/<part>.md`,
`status/<part>.md` and `ai-out/`. Recon over all 7 projects under `10-Projects/`:

| dir | present | missing |
|---|---|---|
| `plans/` | 0 | **7** |
| `status/` | 4 (holding only `repos.txt`) | 3 |
| `ai-out/` | 0 | **7** |

A brain asked to plan therefore has nowhere to write its plan, and its `bash` is denied so it cannot
`mkdir`. It must not solve this by hand-creating directories with `write` — the layout has to come from
one deterministic script so every project gets the identical contract.

> **Overlap note (verified 2026-10-25):** `worktree.sh init` now creates `plans/`, `status/`, `ai-out/`
> vault-side and `.agent/{status,scratch,digests}` repo-side — for projects entering a *code cycle*.
> `vault-init.sh` is the same contract for projects that are not (yet) tied to a repo, plus `--check`.
> The two must produce identical layouts; acceptance case **A9** asserts exactly that: run both tools on
> a temp vault/repo pair and compare the resulting directory trees.

## 2. Slice A — `orchestration/scripts/vault-init.sh` (worker `structure/init-script`)

```
vault-init.sh --project <name|path> [--vault <dir>] [--repos <path>[,<path>…]] [--dry] [--check]
```

Behaviour, all of it required:

1. Resolves `<name>` under `<vault>/10-Projects/` (also searching `10-Projects/Collabs/`), by exact
   directory name first, then case-insensitive substring. **Ambiguous or absent → exit 2 with the list
   of candidates.** No fuzzy guessing: a typo that silently matches the wrong project writes state into
   someone else's folder.
2. Creates, idempotently and only inside that project folder: `plans/`, `status/`, `ai-out/`,
   each containing `.gitkeep` so the empty dir survives a commit. Print one line per element:
   `CREATED plans/` or `EXISTED plans/`. Never delete, never overwrite, never `chmod`.
3. `--repos p1,p2` writes/updates `status/repos.txt` (one repo path per line) — that file is what
   `/triage` recon reads to find the linked code repos. Append-only semantics: add missing lines, keep
   existing ones, sort, dedupe. Never rewrite lines it did not add.
4. `--check` writes nothing. Prints the same lines prefixed `MISSING `/`OK `, exits `0` if complete,
   `1` if anything is missing, `2` if the project cannot be resolved. This is what hygiene tools call.
5. `--dry` prints the `CREATED`/`EXISTED` decisions it *would* take, writes nothing, exit 0.
6. Guards, each fatal with exit 2: the resolved folder is not under a directory containing `10-Projects`;
   the target is not a directory; the target lacks `AGENTS.md` (that means the name resolved to a
   subfolder like `research/`, not a project).
7. Reports state-file linkage without acting on it: if `AGENTS.md` contains no
   `memory/project_*.md` pointer, print `DEBT no state-file pointer in AGENTS.md` and, when exactly one
   `memory/project_*.md` in the vault matches the project name, print
   `SUGGEST memory/project_<x>.md`. **Never edit `AGENTS.md`.** A human decides where its state lives.

Style: `set -euo pipefail`, POSIX-ish bash, no external deps beyond coreutils/git, ≤150 lines, comments
explain *why* (the brain cannot mkdir) not *what*.

## 3. Slice B — vault `.gitignore` (worker `structure/gitignore`)

`$VAULT_ROOT/.gitignore` is missing the generated trees that dominate its dirty state
(2026-10-25: 2171 porcelain entries; `.smart-env/multi` 942, `graphify-out/**` 574+136). Add the
nursery entries so `git status` becomes readable:

```
.smart-env/
graphify-out/
**/graphify-out/
.obsidian/workspace*.json
```

Touch nothing else in the file. Order: append under a `# generated / agent scratch` comment. Do not
`git rm --cached` anything, do not commit — a `--check`-style `git status --porcelain | wc -l` before and
after goes in the report so the effect is visible. This is the only slice that writes outside `daimon/`.

## 4. Acceptance (deterministic; the worker writes this gate first, TDD)

`orchestration/bakeoff/test-vault-init.sh` builds a throwaway vault in `mktemp -d` and asserts:

| # | check |
|---|---|
| A1 | fresh project → all three dirs + `.gitkeep`, exit 0, three `CREATED` lines |
| A2 | run twice → second run prints `EXISTED`, no `CREATED`, byte-identical tree (mtime-independent compare) |
| A3 | `--check` on an old-structure project → exit 1 and names the missing dirs; on a migrated one → exit 0 |
| A4 | `--dry` writes nothing (tree hash unchanged) |
| A5 | unresolvable name → exit 2 + candidate list; ambiguous substring (two matches) → exit 2, picks neither |
| A6 | target without `AGENTS.md` → exit 2, nothing created |
| A7 | `--repos` twice with a duplicate path → `repos.txt` stays deduped, pre-existing foreign line survives |
| A8 | `AGENTS.md` of a project with no pointer → `DEBT` printed and file hash **unchanged** |
| A9 | `vault-init.sh --project P` then `worktree.sh init --repo R --vault P` → the two tools leave the same vault-side layout (no dir one creates that the other misses) |
| B1 | slice B: `git check-ignore -q .smart-env/x` succeeds, `.gitignore` otherwise byte-identical |

The part is green when `bash orchestration/bakeoff/test-vault-init.sh` exits 0 **and**
`bash literature/skills/lit-bib/tests/run_tests.sh` still exits 0 (no regression in the existing gate).

## 5. Explicitly out of scope (do not do this)

- **No `worktree.sh init` on the vault.** It is a git repo with 2171 dirty entries, mostly generated
  caches; a worktree of it is a 1 GB copy and `worktree.sh remove`'s dirty-check becomes useless.
  `vault-init.sh` is the vault-side bootstrap; `worktree.sh` stays for code repos (`daimon`, the-dataset-project, a-collaborator, IEM).
- No editing any `AGENTS.md`, `history.md`, `decisions-log.md`, or `memory/*.md`.
- No commits, no `git add`, no pushing. José lands it.
- No renaming `the-dataset-project` ↔ the stale `PhD-Ch1-the-dataset-project` path (that is task #12, a separate decision).
- Do not "fix" the laptop path in `10-Projects/daimon/project-dashboard.md` (`$HOME/...`) — noted,
  not this slice.

## 6. Follow-on (not for these workers)

After both slices land, run `vault-init.sh --check` over all 7 projects, then `--project` each old one.
Then `/brain <part>` finally has somewhere to write.
