#!/usr/bin/env bash
set -euo pipefail

usage() { printf 'Usage: %s --vault DIR [--dry] [--check]\n' "${0##*/}" >&2; exit 2; }
vault=''
dry=0
check=0
while (($#)); do
  case "$1" in
    --vault) (($# >= 2)) || usage; vault=$2; shift 2 ;;
    --dry) dry=1; shift ;;
    --check) check=1; shift ;;
    *) usage ;;
  esac
done
[[ -n "$vault" && ! ( $dry -eq 1 && $check -eq 1 ) ]] || usage
[[ -d "$vault" ]] || { printf 'REFUSED: not a git repo: %s\n' "$vault" >&2; exit 2; }
root="$(cd "$vault" && pwd -P)"
git_root="$(git -C "$vault" rev-parse --show-toplevel 2>/dev/null)" || {
  printf 'REFUSED: not a git repo: %s\n' "$vault" >&2; exit 2;
}
[[ "$root" == "$git_root" ]] || { printf 'REFUSED: not a git repo root: %s\n' "$vault" >&2; exit 2; }
ignore="$vault/.gitignore"
[[ -f "$ignore" ]] || { printf 'REFUSED: missing %s\n' "$ignore" >&2; exit 2; }
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
template="$script_dir/templates/vault-gitignore.txt"
[[ -f "$template" ]] || { printf 'REFUSED: missing template: %s\n' "$template" >&2; exit 2; }
mapfile -t block < "$template"
((${#block[@]})) || { printf 'REFUSED: empty template: %s\n' "$template" >&2; exit 2; }

# The comment is install marker; check every rule separately to expose partial blocks.
seen=()
for ((i = 0; i < ${#block[@]}; i++)); do seen+=(0); done
while IFS= read -r line || [[ -n "$line" ]]; do
  for ((i = 0; i < ${#block[@]}; i++)); do
    [[ "$line" == "${block[$i]}" ]] && seen[$i]=1
  done
done < "$ignore"
marker_present=${seen[0]}
missing=()
for ((i = 0; i < ${#block[@]}; i++)); do
  ((seen[i])) || missing+=("${block[$i]}")
done

if ((check)); then
  if ((${#missing[@]})); then
    for line in "${missing[@]}"; do printf 'MISSING %s\n' "$line"; done
    exit 1
  fi
  printf 'OK .gitignore block\n'
  exit 0
fi
if ((marker_present)); then printf 'EXISTED .gitignore block\n'; exit 0; fi
printf 'CREATED .gitignore block\n'
((dry)) && exit 0
if [[ -s "$ignore" ]] && [[ "$(tail -c 1 -- "$ignore"; printf x)" != $'\nx' ]]; then
  printf '\n' >> "$ignore"
fi
cat "$template" >> "$ignore"
