#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT/orchestration/scripts/vault-gitignore.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
new_repo() {
  mkdir -p "$1"
  git -C "$1" init -q
  : > "$1/.gitignore"
}

# B1: patterns ignore requested generated trees, but not source.
B1="$TMP/b1"
new_repo "$B1"
"$SCRIPT" --vault "$B1" >/dev/null
for path in .smart-env/multi/x graphify-out/cache/y a/deep/graphify-out/z .obsidian/workspace.json; do
  git -C "$B1" check-ignore -q "$path" || fail "B1 did not ignore $path"
done
git -C "$B1" check-ignore -q src/main.py && fail 'B1 ignored normal source'
printf 'PASS B1\n'

# B2: second install reports EXISTED and leaves bytes unchanged.
B2="$TMP/b2"
new_repo "$B2"
"$SCRIPT" --vault "$B2" >/dev/null
cp "$B2/.gitignore" "$TMP/b2.first"
second="$("$SCRIPT" --vault "$B2")"
[[ "$second" == 'EXISTED .gitignore block' ]] || fail "B2 unexpected output: $second"
cmp -s "$TMP/b2.first" "$B2/.gitignore" || fail 'B2 changed file on second install'
printf 'PASS B2\n'

# B3: foreign bytes stay in place; generated block is appended at end.
B3="$TMP/b3"
new_repo "$B3"
printf '# foreign\r\nvendor/cache/\nlast line' > "$B3/.gitignore"
printf '# foreign\r\nvendor/cache/\nlast line\n# generated / agent scratch\n.smart-env/\ngraphify-out/\n**/graphify-out/\n.obsidian/workspace*.json\n' > "$TMP/b3.expected"
"$SCRIPT" --vault "$B3" >/dev/null
cmp -s "$TMP/b3.expected" "$B3/.gitignore" || fail 'B3 did not preserve and append exact expected bytes'
printf 'PASS B3\n'

# B4: check reports missing entries and never writes; installed check is clean and read-only.
B4="$TMP/b4"
new_repo "$B4"
before="$(sha256sum "$B4/.gitignore")"
if out="$("$SCRIPT" --vault "$B4" --check 2>&1)"; then rc=0; else rc=$?; fi
[[ "$rc" == 1 ]] || fail "B4 absent check exit $rc, expected 1"
for item in '.smart-env/' 'graphify-out/' '**/graphify-out/' '.obsidian/workspace*.json'; do
  [[ "$out" == *"MISSING $item"* ]] || fail "B4 did not name missing $item"
done
[[ "$(sha256sum "$B4/.gitignore")" == "$before" ]] || fail 'B4 absent check wrote file'
"$SCRIPT" --vault "$B4" >/dev/null
before="$(sha256sum "$B4/.gitignore")"
"$SCRIPT" --vault "$B4" --check >/dev/null || fail 'B4 blocked check failed'
[[ "$(sha256sum "$B4/.gitignore")" == "$before" ]] || fail 'B4 blocked check wrote file'
B4_PARTIAL="$TMP/b4-partial"
new_repo "$B4_PARTIAL"
printf '# generated / agent scratch\n' > "$B4_PARTIAL/.gitignore"
before="$(sha256sum "$B4_PARTIAL/.gitignore")"
if out="$("$SCRIPT" --vault "$B4_PARTIAL" --check 2>&1)"; then rc=0; else rc=$?; fi
[[ "$rc" == 1 && "$out" == *'MISSING .smart-env/'* ]] || fail 'B4 partial marker did not report missing rules'
out="$("$SCRIPT" --vault "$B4_PARTIAL")"
[[ "$out" == 'EXISTED .gitignore block' ]] || fail "B4 partial marker output: $out"
[[ "$(sha256sum "$B4_PARTIAL/.gitignore")" == "$before" ]] || fail 'B4 partial marker was rewritten'
printf 'PASS B4\n'

# B5: dry-run matches apply decision and preserves bytes.
B5="$TMP/b5"
new_repo "$B5"
before="$(sha256sum "$B5/.gitignore")"
dry="$("$SCRIPT" --vault "$B5" --dry)"
[[ "$dry" == 'CREATED .gitignore block' ]] || fail "B5 unexpected dry output: $dry"
[[ "$(sha256sum "$B5/.gitignore")" == "$before" ]] || fail 'B5 dry-run changed file'
apply="$("$SCRIPT" --vault "$B5")"
[[ "$dry" == "$apply" ]] || fail "B5 dry/apply decisions differ: $dry / $apply"
printf 'PASS B5\n'

# B6: invalid targets and missing template refuse with exit 2 and no writes.
B6="$TMP/b6"
mkdir -p "$B6/nonrepo"
printf 'keep\n' > "$B6/nonrepo/.gitignore"
if "$SCRIPT" --vault "$B6/nonrepo" >/dev/null 2>&1; then rc=0; else rc=$?; fi
[[ "$rc" == 2 ]] || fail "B6 non-git exit $rc, expected 2"
[[ "$(<"$B6/nonrepo/.gitignore")" == keep ]] || fail 'B6 non-git changed file'
B6_NOIGNORE="$B6/noignore"
mkdir -p "$B6_NOIGNORE"
git -C "$B6_NOIGNORE" init -q
if "$SCRIPT" --vault "$B6_NOIGNORE" >/dev/null 2>&1; then rc=0; else rc=$?; fi
[[ "$rc" == 2 && ! -e "$B6_NOIGNORE/.gitignore" ]] || fail 'B6 absent .gitignore did not refuse cleanly'
mkdir -p "$B6/fake-script-dir" "$B6/notemplate"
git -C "$B6/notemplate" init -q
: > "$B6/notemplate/.gitignore"
cp "$SCRIPT" "$B6/fake-script-dir/vault-gitignore.sh"
if "$B6/fake-script-dir/vault-gitignore.sh" --vault "$B6/notemplate" >/dev/null 2>&1; then rc=0; else rc=$?; fi
[[ "$rc" == 2 && ! -s "$B6/notemplate/.gitignore" ]] || fail 'B6 missing template did not refuse without writes'
printf 'PASS B6\n'

# Guard the implementation contract as part of this gate.
grep -Fqx 'set -euo pipefail' "$SCRIPT" || fail 'script lacks set -euo pipefail'
lines="$(wc -l < "$SCRIPT")"
(( lines <= 120 )) || fail "script is $lines lines, maximum 120"
bash -n "$SCRIPT"
printf 'PASS script contract (%s lines)\n' "$lines"
printf 'PASS all B1-B6\n'
