#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VAULT_INIT="$ROOT/orchestration/scripts/vault-init.sh"
WORKTREE="$ROOT/orchestration/scripts/worktree.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
VAULT="$TMP/vault"
PROJECTS="$VAULT/10-Projects"
mkdir -p "$PROJECTS/Collabs"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS $1: $2"; }
expect_code() {
  local want="$1"; shift
  local output code
  set +e
  output="$("$@" 2>&1)"
  code=$?
  set -e
  [[ "$code" -eq "$want" ]] || fail "expected exit $want, got $code: $output"
  printf '%s' "$output"
}
contains() { grep -Fq -- "$2" <<<"$1" || fail "missing '$2' in: $1"; }
not_contains() { ! grep -Fq -- "$2" <<<"$1" || fail "unexpected '$2' in: $1"; }
project() {
  mkdir -p "$PROJECTS/$1"
  printf 'Project instructions\n' > "$PROJECTS/$1/AGENTS.md"
}
fingerprint() {
  ( cd "$1" && {
      find . -mindepth 1 -printf '%y %p\n' | LC_ALL=C sort
      find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum
    } ) | sha256sum | awk '{print $1}'
}

# A1: first bootstrap creates the contract and its commit-preserving sentinels.
project Fresh
out="$(expect_code 0 "$VAULT_INIT" --project Fresh --vault "$VAULT")"
for d in plans status ai-out; do
  [[ -d "$PROJECTS/Fresh/$d" && -f "$PROJECTS/Fresh/$d/.gitkeep" ]] || fail "A1 missing $d/.gitkeep"
  contains "$out" "CREATED $d/"
done
[[ "$(grep -c '^CREATED ' <<<"$out")" -eq 3 ]] || fail "A1 expected three CREATED lines: $out"
pass A1 'fresh project creates three directories and sentinels'

# A2: second bootstrap is idempotent, including file contents and directory set.
before="$(fingerprint "$PROJECTS/Fresh")"
out="$(expect_code 0 "$VAULT_INIT" --project Fresh --vault "$VAULT")"
[[ "$(grep -c '^EXISTED ' <<<"$out")" -eq 3 ]] || fail "A2 expected three EXISTED lines: $out"
not_contains "$out" 'CREATED '
[[ "$(fingerprint "$PROJECTS/Fresh")" == "$before" ]] || fail 'A2 tree changed on second run'
pass A2 'repeat run reports EXISTED and leaves tree unchanged'

# A3: check-only reports missing elements, then succeeds on a complete layout.
project Old
out="$(expect_code 1 "$VAULT_INIT" --project Old --vault "$VAULT" --check)"
for d in plans status ai-out; do contains "$out" "MISSING $d/"; done
[[ ! -e "$PROJECTS/Old/plans" && ! -e "$PROJECTS/Old/status" && ! -e "$PROJECTS/Old/ai-out" ]] || fail 'A3 --check wrote files'
out="$(expect_code 0 "$VAULT_INIT" --project Fresh --vault "$VAULT" --check)"
for d in plans status ai-out; do contains "$out" "OK $d/"; done
pass A3 '--check distinguishes incomplete and complete layouts without writing'

# A4: dry run reports planned actions and preserves exact tree contents.
before="$(fingerprint "$PROJECTS/Old")"
out="$(expect_code 0 "$VAULT_INIT" --project Old --vault "$VAULT" --dry)"
for d in plans status ai-out; do contains "$out" "CREATED $d/"; done
[[ "$(fingerprint "$PROJECTS/Old")" == "$before" ]] || fail 'A4 --dry changed project tree'
pass A4 '--dry reports decisions without writing'

# A5: typo and ambiguous substring both fail closed and show candidate names.
project Alpha-Foo
project Beta-Foo
out="$(expect_code 2 "$VAULT_INIT" --project ZzzMissing --vault "$VAULT")"
contains "$out" 'Alpha-Foo'
contains "$out" 'Beta-Foo'
out="$(expect_code 2 "$VAULT_INIT" --project Foo --vault "$VAULT")"
contains "$out" 'Alpha-Foo'
contains "$out" 'Beta-Foo'
[[ ! -e "$PROJECTS/Alpha-Foo/plans" && ! -e "$PROJECTS/Beta-Foo/plans" ]] || fail 'A5 ambiguous lookup wrote files'
mkdir -p "$PROJECTS/Collabs/Partner-Project"
printf 'Project instructions\n' > "$PROJECTS/Collabs/Partner-Project/AGENTS.md"
out="$(expect_code 0 "$VAULT_INIT" --project partner --vault "$VAULT")"
contains "$out" 'CREATED plans/'
pass A5 'unresolved and ambiguous names fail closed; Collabs substring resolves'

# A6: a directory that is not a project must not be bootstrapped.
mkdir -p "$PROJECTS/NotAProject"
out="$(expect_code 2 "$VAULT_INIT" --project NotAProject --vault "$VAULT")"
contains "$out" 'AGENTS.md'
[[ ! -e "$PROJECTS/NotAProject/plans" ]] || fail 'A6 created layout without AGENTS.md'
mkdir -p "$TMP/outside"
printf 'Not a vault project\n' > "$TMP/outside/AGENTS.md"
out="$(expect_code 2 "$VAULT_INIT" --project "$TMP/outside" --vault "$VAULT")"
contains "$out" 'not under'
printf 'not a directory\n' > "$PROJECTS/NotDirectory"
out="$(expect_code 2 "$VAULT_INIT" --project "$PROJECTS/NotDirectory" --vault "$VAULT")"
contains "$out" 'not a directory'
pass A6 'missing AGENTS, non-project path, and non-directory rejected before writes'

# A7: repository links merge additively, sorted and deduplicated.
project Repos
mkdir -p "$PROJECTS/Repos/status"
printf 'foreign-repo\nrepo-b' > "$PROJECTS/Repos/status/repos.txt"
"$VAULT_INIT" --project Repos --vault "$VAULT" --repos 'repo-a,repo-b' >/dev/null
"$VAULT_INIT" --project Repos --vault "$VAULT" --repos 'repo-c,repo-a' >/dev/null
expected=$'foreign-repo\nrepo-a\nrepo-b\nrepo-c'
[[ "$(cat "$PROJECTS/Repos/status/repos.txt")" == "$expected" ]] || fail "A7 repos.txt differs: $(cat "$PROJECTS/Repos/status/repos.txt")"
pass A7 '--repos adds, sorts, deduplicates, and preserves existing line'

# A8: linkage advice is read-only, even when a matching state note exists.
project StatePointer
mkdir -p "$VAULT/memory"
printf 'No state pointer here.\n' > "$PROJECTS/StatePointer/AGENTS.md"
printf 'private state\n' > "$VAULT/memory/project_statepointer.md"
before="$(sha256sum "$PROJECTS/StatePointer/AGENTS.md" | awk '{print $1}')"
out="$(expect_code 0 "$VAULT_INIT" --project StatePointer --vault "$VAULT")"
contains "$out" 'DEBT no state-file pointer in AGENTS.md'
contains "$out" 'SUGGEST memory/project_statepointer.md'
[[ "$(sha256sum "$PROJECTS/StatePointer/AGENTS.md" | awk '{print $1}')" == "$before" ]] || fail 'A8 AGENTS.md changed'
pass A8 'state-file advice does not modify AGENTS.md'

# A9: the standalone bootstrap and worktree init create same vault-side directories.
mkdir -p "$PROJECTS/P"
printf 'Project instructions\n' > "$PROJECTS/P/AGENTS.md"
"$VAULT_INIT" --project P --vault "$VAULT" >/dev/null
left="$(cd "$PROJECTS/P" && find . -type d -printf '%P\n' | LC_ALL=C sort)"
mkdir -p "$TMP/repo"
git -C "$TMP/repo" init -q
"$WORKTREE" init --repo "$TMP/repo" --vault "$PROJECTS/P" >/dev/null
right="$(cd "$PROJECTS/P" && find . -type d -printf '%P\n' | LC_ALL=C sort)"
[[ "$left" == "$right" ]] || fail 'A9 vault-side directory trees differ'
for d in plans status ai-out; do [[ -d "$PROJECTS/P/$d" ]] || fail "A9 missing $d/"; done
pass A9 'vault-init and worktree init leave matching vault-side directory layout'

# A10: an exact directory name wins over another project's substring match.
project ExactTarget
project Longer-ExactTarget
out="$(expect_code 0 "$VAULT_INIT" --project ExactTarget --vault "$VAULT")"
[[ -f "$PROJECTS/ExactTarget/plans/.gitkeep" ]] || fail 'A10 exact match was not initialized'
[[ ! -e "$PROJECTS/Longer-ExactTarget/plans" ]] || fail 'A10 substring candidate was initialized'
pass A10 'exact-name match beats substring candidate'

# A11: adding a missing sentinel must preserve unrelated content and directory mode.
project Preserve
mkdir -p "$PROJECTS/Preserve/plans"
printf 'keep this data\n' > "$PROJECTS/Preserve/plans/existing.txt"
chmod 0751 "$PROJECTS/Preserve/plans"
mode_before="$(stat -c '%a' "$PROJECTS/Preserve/plans")"
content_before="$(sha256sum "$PROJECTS/Preserve/plans/existing.txt" | awk '{print $1}')"
"$VAULT_INIT" --project Preserve --vault "$VAULT" >/dev/null
[[ "$(stat -c '%a' "$PROJECTS/Preserve/plans")" == "$mode_before" ]] || fail 'A11 plans/ mode changed'
[[ "$(sha256sum "$PROJECTS/Preserve/plans/existing.txt" | awk '{print $1}')" == "$content_before" ]] || fail 'A11 existing file content changed'
pass A11 'existing content and directory mode are preserved'

# A12: a directory without its sentinel remains incomplete until the sentinel is created.
project Partial
mkdir -p "$PROJECTS/Partial/plans"
out="$(expect_code 1 "$VAULT_INIT" --project Partial --vault "$VAULT" --check)"
contains "$out" 'MISSING plans/'
[[ ! -e "$PROJECTS/Partial/plans/.gitkeep" ]] || fail 'A12 --check created missing sentinel'
out="$(expect_code 0 "$VAULT_INIT" --project Partial --vault "$VAULT" --dry)"
contains "$out" 'EXISTED plans/'
not_contains "$out" 'CREATED plans/'
[[ ! -f "$PROJECTS/Partial/plans/.gitkeep" ]] || fail 'A12 --dry created missing sentinel'
out="$(expect_code 0 "$VAULT_INIT" --project Partial --vault "$VAULT")"
contains "$out" 'EXISTED plans/'
[[ -f "$PROJECTS/Partial/plans/.gitkeep" ]] || fail 'A12 init did not create sentinel'
pass A12 'partial directory is missing in check; existing directory reported during repair'

# A13: unresolved and ambiguous check requests use resolver exit code 2, not missing-layout 1.
out="$(expect_code 2 "$VAULT_INIT" --project NeverThere --vault "$VAULT" --check)"
contains "$out" 'Candidates:'
out="$(expect_code 2 "$VAULT_INIT" --project Foo --vault "$VAULT" --check)"
contains "$out" 'Alpha-Foo'
contains "$out" 'Beta-Foo'
pass A13 '--check returns 2 for unresolved and ambiguous projects'

# A14: --repos participates in check status and dry run never writes links.
out="$(expect_code 0 "$VAULT_INIT" --project Repos --vault "$VAULT" --repos repo-a --check)"
contains "$out" 'OK status/repos.txt'
out="$(expect_code 1 "$VAULT_INIT" --project Repos --vault "$VAULT" --repos repo-new --check)"
contains "$out" 'MISSING status/repos.txt'
before="$(fingerprint "$PROJECTS/Repos")"
out="$(expect_code 0 "$VAULT_INIT" --project Repos --vault "$VAULT" --repos repo-dry --dry)"
contains "$out" 'UPDATED status/repos.txt'
[[ "$(fingerprint "$PROJECTS/Repos")" == "$before" ]] || fail 'A14 --dry changed repos project'
not_contains "$(cat "$PROJECTS/Repos/status/repos.txt")" 'repo-dry'
pass A14 '--check validates requested repo links; --dry leaves them untouched'

# A15: pointer presence suppresses debt; zero or multiple note matches suppress suggestion.
project PointerPresent
printf 'Read memory/project_pointerpresent.md for state.\n' > "$PROJECTS/PointerPresent/AGENTS.md"
out="$(expect_code 0 "$VAULT_INIT" --project PointerPresent --vault "$VAULT")"
not_contains "$out" 'DEBT '
project NoMemory
out="$(expect_code 0 "$VAULT_INIT" --project NoMemory --vault "$VAULT")"
contains "$out" 'DEBT no state-file pointer in AGENTS.md'
not_contains "$out" 'SUGGEST '
project MultiMemory
printf 'one\n' > "$VAULT/memory/project_multimemory.md"
printf 'two\n' > "$VAULT/memory/project_multimemory_notes.md"
out="$(expect_code 0 "$VAULT_INIT" --project MultiMemory --vault "$VAULT")"
contains "$out" 'DEBT no state-file pointer in AGENTS.md'
not_contains "$out" 'SUGGEST '
pass A15 'pointer suppresses debt; zero or multiple matches suppress suggestion'

# A16: preserve the documented compact-script guard.
lines="$(wc -l < "$VAULT_INIT")"
[[ "$lines" -le 150 ]] || fail "A16 script has $lines lines (limit 150)"
grep -Fqx 'set -euo pipefail' "$VAULT_INIT" || fail 'A16 strict shell mode missing'
pass A16 'script stays within 150 lines and enables strict shell mode'

echo 'PASS all A1-A16'
