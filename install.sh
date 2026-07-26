#!/bin/bash
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ok(){ printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn(){ printf '    \033[33m!\033[0m %s\n' "$*"; }
printf '\033[1;36m==>\033[0m RAPP Tools\n'
[ -d "$HOME/.brainstem/src/rapp_brainstem" ] && ok "brainstem found" \
  || warn "no brainstem at ~/.brainstem — hatching will not work until one exists"
mkdir -p "$HOME/.local/bin"; ln -sfn "$SRC/rapptools" "$HOME/.local/bin/rapptools"
ok "$HOME/.local/bin/rapptools"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) warn "add ~/.local/bin to your PATH" ;; esac
"$SRC/rapptools" list
