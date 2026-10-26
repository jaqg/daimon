#!/usr/bin/env bash
# Bootstrap vault layout deterministically; agents cannot create these directories themselves.
set -euo pipefail

die() { echo "vault-init: $*" >&2; exit 2; }
PROJECT='' VAULT="${VAULT_ROOT:-$HOME/Documents/vault}" REPOS='' HAVE_REPOS=0 MODE=apply
while (($#)); do
  case "$1" in
    --project|--vault|--repos)
      (($# >= 2)) || die "$1 requires a value"
      case "$1" in
        --project) PROJECT="$2";;
        --vault) VAULT="$2";;
        --repos) REPOS="$2"; HAVE_REPOS=1;;
      esac
      shift 2;;
    --dry) [[ "$MODE" == apply ]] || die '--dry and --check are exclusive'; MODE=dry; shift;;
    --check) [[ "$MODE" == apply ]] || die '--dry and --check are exclusive'; MODE=check; shift;;
    *) die "unknown argument: $1";;
  esac
done
[[ -n "$PROJECT" ]] || die '--project required'
[[ -d "$VAULT" ]] || die "vault is not a directory: $VAULT"
VAULT="$(realpath -e -- "$VAULT")"
PROJECTS="$VAULT/10-Projects"
[[ -d "$PROJECTS" ]] || die "missing $PROJECTS"
PROJECTS="$(realpath -e -- "$PROJECTS")"

if ((HAVE_REPOS)); then
  IFS=, read -r -a REPO_PATHS <<< "$REPOS"
  ((${#REPO_PATHS[@]})) || die '--repos needs at least one path'
  for r in "${REPO_PATHS[@]}"; do [[ -n "$r" ]] || die '--repos contains an empty path'; done
else
  REPO_PATHS=()
fi

mapfile -d '' CANDIDATES < <(
  for base in "$PROJECTS" "$PROJECTS/Collabs"; do
    [[ -d "$base" ]] || continue
    while IFS= read -r -d '' path; do
      [[ "$base" != "$PROJECTS" || "${path##*/}" != Collabs ]] || continue
      printf '%s\0' "${path#"$PROJECTS"/}"
    done < <(find "$base" -mindepth 1 -maxdepth 1 -type d -print0)
  done | LC_ALL=C sort -z
)
show_candidates() {
  echo "vault-init: $1" >&2
  echo 'Candidates:' >&2
  if ((${#CANDIDATES[@]})); then printf '  %s\n' "${CANDIDATES[@]}" >&2; else echo '  (none)' >&2; fi
  exit 2
}
TARGET=''
if [[ "$PROJECT" == */* ]]; then
  if [[ "$PROJECT" == /* ]]; then TARGET="$PROJECT"
  elif [[ -e "$PROJECT" ]]; then TARGET="$PROJECT"
  elif [[ "$PROJECT" == 10-Projects/* ]]; then TARGET="$VAULT/$PROJECT"
  else TARGET="$PROJECTS/$PROJECT"; fi
  [[ -e "$TARGET" ]] || show_candidates "cannot resolve '$PROJECT'"
else
  exact=() matches=()
  for candidate in "${CANDIDATES[@]}"; do
    name="${candidate##*/}"
    [[ "$name" == "$PROJECT" ]] && exact+=("$candidate")
  done
  if ((${#exact[@]} == 1)); then TARGET="$PROJECTS/${exact[0]}"
  elif ((${#exact[@]} > 1)); then show_candidates "ambiguous exact project '$PROJECT'"
  else
    needle="${PROJECT,,}"
    for candidate in "${CANDIDATES[@]}"; do
      name="${candidate##*/}"; [[ "${name,,}" == *"$needle"* ]] && matches+=("$candidate")
    done
    ((${#matches[@]} == 1)) || show_candidates "${#matches[@]} matches for '$PROJECT'"
    TARGET="$PROJECTS/${matches[0]}"
  fi
fi
TARGET="$(realpath -e -- "$TARGET")" || show_candidates "cannot resolve '$PROJECT'"
[[ "$TARGET" != "$PROJECTS" && "$TARGET" == "$PROJECTS/"* ]] || die "project is not under $PROJECTS: $TARGET"
[[ -d "$TARGET" ]] || die "target is not a directory: $TARGET"
[[ -f "$TARGET/AGENTS.md" ]] || die "target lacks AGENTS.md: $TARGET"
DIRS=(plans status ai-out)
for d in "${DIRS[@]}"; do
  [[ ! -L "$TARGET/$d" && ! -L "$TARGET/$d/.gitkeep" ]] || die "refusing symlink in managed layout: $d"
  [[ ! -e "$TARGET/$d" || -d "$TARGET/$d" ]] || die "not a directory: $d/"
  [[ ! -e "$TARGET/$d/.gitkeep" || -f "$TARGET/$d/.gitkeep" ]] || die "not a file: $d/.gitkeep"
done
REPO_FILE="$TARGET/status/repos.txt"
if ((HAVE_REPOS)); then
  [[ ! -L "$REPO_FILE" ]] || die 'refusing symlink: status/repos.txt'
  [[ ! -e "$REPO_FILE" || -f "$REPO_FILE" ]] || die 'not a file: status/repos.txt'
fi
MISSING=0
for d in "${DIRS[@]}"; do
  path="$TARGET/$d"; exists=0; [[ -d "$path" ]] && exists=1
  complete=1; [[ -d "$path" && -f "$path/.gitkeep" ]] || complete=0
  if [[ "$MODE" == check ]]; then
    if ((complete)); then echo "OK $d/"; else echo "MISSING $d/"; MISSING=1; fi
  elif [[ "$MODE" == dry ]]; then
    ((exists)) && echo "EXISTED $d/" || echo "CREATED $d/"
  else
    ((exists)) || mkdir -p -- "$path" || die "cannot create $d/"
    [[ -e "$path/.gitkeep" ]] || { (set -o noclobber; : > "$path/.gitkeep") 2>/dev/null || die "cannot create $d/.gitkeep"; }
    ((exists)) && echo "EXISTED $d/" || echo "CREATED $d/"
  fi
done
repo_complete=1
if ((HAVE_REPOS)); then
  if [[ ! -f "$REPO_FILE" ]]; then repo_complete=0
  else for r in "${REPO_PATHS[@]}"; do grep -Fqx -- "$r" "$REPO_FILE" || repo_complete=0; done; fi
  if [[ "$MODE" == check ]]; then
    if ((repo_complete)); then echo 'OK status/repos.txt'; else echo 'MISSING status/repos.txt'; MISSING=1; fi
  elif [[ "$MODE" == dry ]]; then
    if ((repo_complete)); then echo 'EXISTED status/repos.txt'
    elif [[ -e "$REPO_FILE" ]]; then echo 'UPDATED status/repos.txt'
    else echo 'CREATED status/repos.txt'; fi
  else
    tmp="$(mktemp "$TARGET/status/.repos.XXXXXX")" || die 'cannot stage repos.txt'
    if [[ -f "$REPO_FILE" ]]; then
      while IFS= read -r line || [[ -n "$line" ]]; do printf '%s\n' "$line"; done < "$REPO_FILE" > "$tmp"
    fi
    for r in "${REPO_PATHS[@]}"; do grep -Fqx -- "$r" "$tmp" || printf '%s\n' "$r" >> "$tmp"; done
    LC_ALL=C sort -u "$tmp" -o "$tmp"
    if [[ -f "$REPO_FILE" ]] && cmp -s "$tmp" "$REPO_FILE"; then
      rm -f -- "$tmp"; echo 'EXISTED status/repos.txt'
    else
      if [[ -e "$REPO_FILE" ]]; then echo 'UPDATED status/repos.txt'; else echo 'CREATED status/repos.txt'; fi
      mv -f -- "$tmp" "$REPO_FILE"
    fi
  fi
fi
if ! grep -Eq 'memory/project_[^/[:space:]]+\.md' "$TARGET/AGENTS.md"; then
  echo 'DEBT no state-file pointer in AGENTS.md'
  slug="${TARGET##*/}"; slug="${slug,,}"; slug="${slug//-/_}"; slug="${slug// /_}"
  found=()
  if [[ -d "$VAULT/memory" ]]; then
    while IFS= read -r -d '' note; do
      name="${note##*/project_}"; name="${name%.md}"; name="${name,,}"
      name="${name//-/_}"; name="${name// /_}"
      [[ "$name" == "$slug" || "$name" == "$slug"_* ]] && found+=("${note#"$VAULT"/}")
    done < <(find "$VAULT/memory" -maxdepth 1 -type f -name 'project_*.md' -print0)
  fi
  ((${#found[@]} == 1)) && echo "SUGGEST ${found[0]}"
fi
[[ "$MODE" != check || $MISSING -eq 0 ]] || exit 1
