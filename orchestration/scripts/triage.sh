#!/usr/bin/env bash
# triage.sh — deterministic project recon for the brain tier.
#
# Why this exists as a script: `/triage` used to hand the brain a block of `find | ls | grep | cat`
# one-liners as its procedure — and the brain's gate denies bash. The prompt described a sequence the
# role physically could not run, so the first thing every triage cycle did was hit a tool-deny
# (José, 2026-10-26). The facts are all mechanical (which dirs exist, where the state pointer points,
# what the linked repos are doing), so they belong in a script the gate already allows, not in a
# brain session transcribing directory listings through `read` at cache-read prices.
#
# Output is pointers and counts, never file bodies: the brain reads the two or three files this names.
set -uo pipefail

die() { echo "triage: $*" >&2; exit "${2:-4}"; }

PROJ='' VAULT=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vault) VAULT="${2:-}"; shift 2 ;;
    --help|-h) echo "usage: triage.sh <project> [--vault <path>]   (project = name under 10-Projects/, fuzzy match allowed)"; exit 0 ;;
    -*) die "unknown flag: $1" ;;
    *) [[ -z "$PROJ" ]] && PROJ="$1" || die "unexpected argument: $1"; shift ;;
  esac
done
[[ -n "$PROJ" ]] || die "usage: triage.sh <project> [--vault <path>]"

# Vault resolution, in the order the rest of the machinery agreed on: explicit flag, then environment,
# then the per-machine file deploy.sh writes, then a small candidate list. vault-init.sh still defaults
# to $HOME/Documents/vault and so invented a nonexistent path (task #22); do not copy that behaviour here.
vault_root() {
  if [[ -n "$VAULT" ]]; then printf '%s\n' "${VAULT%/}"; return 0; fi
  if [[ -n "${VAULT_ROOT:-}" ]]; then printf '%s\n' "${VAULT_ROOT%/}"; return 0; fi
  local f="$HOME/.config/pi/vault-root"
  if [[ -r "$f" ]]; then local r; r="$(head -1 "$f" | tr -d '[:space:]')"; [[ -n "$r" ]] && { printf '%s\n' "$r"; return 0; }; fi
  local c
  for c in "$HOME/Documents/Universidad/vault" "$HOME/Documents/vault"; do
    [[ -d "$c" ]] && { printf '%s\n' "$c"; return 0; }
  done
  return 1
}

V="$(vault_root)" || die "cannot find the vault: pass --vault <path>, set VAULT_ROOT, or write the path to $HOME/.config/pi/vault-root"
[[ -d "$V" ]] || die "vault is not a directory: $V"
ROOT="$V/10-Projects"
[[ -d "$ROOT" ]] || die "no 10-Projects/ under $V"

# Exact match first, then case-insensitive anywhere at depth ≤2 (Collabs/ lives one level down).
P=''
if [[ -d "$ROOT/$PROJ" ]]; then
  P="$ROOT/$PROJ"
else
  mapfile -t HITS < <(find "$ROOT" -maxdepth 2 -type d -iname "*$PROJ*" 2>/dev/null | sort)
  [[ ${#HITS[@]} -eq 1 ]] || die "project '$PROJ' is not a unique match (${#HITS[@]} hits): $(printf '%s ' "${HITS[@]:-none}")" 
  P="${HITS[0]}"
fi
REL="${P#$ROOT/}"
echo "VAULT=$V"
echo "PROJECT=$P"
echo "REL=$REL"

# State pointer: the AGENTS.md line that names this project's memory file. Missing pointer = debt, not
# a missing project.
STATE='NONE'
if [[ -f "$P/AGENTS.md" ]]; then
  S="$(grep -m1 -oE 'memory/project_[A-Za-z0-9_]*\.md' "$P/AGENTS.md" || true)"
  [[ -n "$S" ]] && STATE="$V/${S%%:*}"
fi
echo "STATE=$STATE"

# Structure generation: the four dirs the current contract expects. Present-but-empty counts too.
echo "STRUCTURE"
for d in plans status ai-out handoffs; do
  if [[ -d "$P/$d" ]]; then echo "  $d/ present ($(find "$P/$d" -type f | wc -l | tr -d ' ') files)"
  else echo "  $d/ MISSING"; fi
done

# Where the knowledge actually lives, with sizes so the brain can choose what to read.
for f in project-dashboard.md history.md open-questions.md; do
  [[ -f "$P/$f" ]] && echo "DOC=$P/$f ($(wc -l < "$P/$f" | tr -d ' ') lines)" || echo "DOC=$P/$f (absent)"
done
[[ -f "$P/handoffs/next-session-context.md" ]] && echo "DOC=$P/handoffs/next-session-context.md"
[[ -d "$P/plans" ]] && find "$P/plans" -maxdepth 1 -name '*.md' -printf 'PLAN=%f (%s bytes)\n' 2>/dev/null | sort

[[ -f "$P/history.md" ]] && { echo "LAST SECTIONS IN history.md"; grep -nE '^#{2,3} ' "$P/history.md" | tail -6; }
[[ -f "$P/open-questions.md" ]] && echo "OPEN QUESTIONS=$(grep -cE '^[[:space:]]*-[[:space:]]*\[ \]' "$P/open-questions.md" || true)"

# Part rollups are derived output: name them, quote their first line, do not re-summarise them.
shopt -s nullglob
for f in "$P"/status/*.md; do
  echo "ROLLUP=$(basename "$f") :: $(head -1 "$f" | cut -c1-90)"
done

# Linked repos: the facts a human would otherwise run `git -C ...` for. Comment lines in the file start
# with `# repo:` and are documentation, not a declaration: an earlier version regex-scraped paths out of
# them and reported a real-looking "NOT A REPO" for a project that has no repos declared yet.
if [[ -f "$P/status/repos.txt" ]]; then
  echo "REPOS"
  n=0
  while IFS= read -r r; do
    [[ -z "${r// }" || "${r:0:1}" == "#" ]] && continue   # keep counting comments: "none declared" is a fact
    n=$((n+1))
    [[ "$r" == "~/"* ]] && r="$HOME/${r#~/}"
    [[ "$r" != /* ]] && r="$V/$r"
    if git -C "$r" rev-parse --git-dir >/dev/null 2>&1; then
      B="$(git -C "$r" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
      D="$(git -C "$r" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
      U="$(git -C "$r" log --oneline -1 2>/dev/null || echo 'no commits')"
      echo "  $r  branch=$B dirty=$D  last: ${U:0:70}"
    else
      echo "  $r  NOT A REPO (verify the path in status/repos.txt)"
    fi
  done < <(sed -e 's/^[[:space:]]*//' -e '/^#/d' -e '/^\[/d' -e 's/^repo:[[:space:]]*//' -e 's/[[:space:]]*$//' "$P/status/repos.txt")
  [[ $n -eq 0 ]] && echo "  none declared — only format comments. Registering the repo is a planning decision, not recon."
fi

# Debt fixes are printed as the exact command, with the vault already resolved, because the brain may
# not run it and José should not have to reconstruct the path.
DEBT=()
for d in plans status ai-out; do [[ -d "$P/$d" ]] || DEBT+=("$d/"); done
[[ "$STATE" == NONE ]] && DEBT+=("memory pointer")
if [[ ${#DEBT[@]} -gt 0 ]]; then
  echo "STRUCTURE DEBT: ${DEBT[*]}"
  # The gate's allow-list only admits the deployed path, so print that one; if the script has not landed
  # yet (it is still an unmerged agent branch), say so instead of printing a command that cannot run.
  VI="$HOME/.pi/agent/scripts/vault-init.sh"
  if [[ -e "$VI" ]]; then
    echo "next-command[operator]: bash $VI --project $REL --vault $V"
  else
    echo "next-command[operator]: bash <repo>/orchestration/scripts/vault-init.sh --project $REL --vault $V"
    echo "note: vault-init.sh is not installed at $VI yet — the slice that ships it is still unmerged."
  fi
  echo "note: vault-init.sh is idempotent and writes nothing that already exists; the brain cannot run it."
else
  echo "STRUCTURE DEBT: none"
fi
