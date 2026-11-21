#!/bin/bash
# Entry point of a product image. It lives in /home/ubuntu/.init/ with the aids (aids/).
#   BENCH_SLOT  required: the slot id of a tree, the folder <slots root>/<slot id>/<product>
#   BENCH_AID   none (default), skill (the skill folder into <tree>/.claude/skills/idesense/)
#               or rule (rule.txt as <tree>/CLAUDE.md)
# It installs the aid, removes each other slot folder and its own folder, unsets each variable whose
# name starts with BENCH, and runs `claude` in the tree with each argument of the container command.
# An unknown slot or aid exits 2 before any removal, and so does a copy of this script that is not
# in its init folder. The image sets BENCH_SLOTS_ROOT, the slots root (default /home/ubuntu/dev/ws);
# BENCH_INIT is set only by the unit tests.
# The body is one function, called in the last line: the removal of this file does not break the run.

main() {
  set -euo pipefail
  local root="${BENCH_SLOTS_ROOT:-/home/ubuntu/dev/ws}"
  local init="${BENCH_INIT:-/home/ubuntu/.init}"
  local slot="${BENCH_SLOT:-}"
  local aid="${BENCH_AID:-none}"

  if [ "$(readlink -f "$0")" != "$(readlink -f "$init")/entry.sh" ]; then
    echo "entry: this script runs only as $init/entry.sh" >&2
    exit 2
  fi
  case "$slot" in
    [0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
    *)
      echo "entry: unknown slot '$slot'" >&2
      exit 2 ;;
  esac
  local found=("$root/$slot"/*/)
  if [ "${#found[@]}" -ne 1 ] || [ ! -d "${found[0]}" ]; then
    echo "entry: unknown slot '$slot'" >&2
    exit 2
  fi
  local tree="${found[0]%/}"
  case "$aid" in
    none | skill | rule) ;;
    *)
      echo "entry: unknown aid '$aid'" >&2
      exit 2 ;;
  esac

  if [ "$aid" = skill ]; then
    mkdir -p "$tree/.claude/skills"
    cp -R "$init/aids/skill/idesense" "$tree/.claude/skills/idesense"
  elif [ "$aid" = rule ]; then
    cp "$init/aids/rule.txt" "$tree/CLAUDE.md"
  fi
  local other
  for other in "$root"/*/; do
    if [ "${other%/}" != "$root/$slot" ]; then
      rm -rf "${other%/}"
    fi
  done
  rm -rf "$init"

  cd "$tree"
  local name
  for name in "${!BENCH@}"; do
    unset "$name"
  done
  exec claude "$@"
}

main "$@"
