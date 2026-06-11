#!/usr/bin/env bash
# Install Claude Code global skills from this repo.
# Usage: bash tools/skills/install.sh [--dry-run]
#
# Skills are installed to ~/.claude/skills/ so they're available in any project.
# The path to confluence_fetch.py is auto-resolved to this repo's tools/ directory.

set -euo pipefail

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SKILLS_DEST="$HOME/.claude/skills"
CONFLUENCE_TOOL="$REPO_ROOT/tools/confluence_fetch.py"

log() { echo "[install-skills] $*"; }
run() {
  if $DRY_RUN; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

log "Repo root  : $REPO_ROOT"
log "Skills src : $SCRIPT_DIR"
log "Skills dest: $SKILLS_DEST"
log "Confluence tool: $CONFLUENCE_TOOL"
echo ""

SKILLS=("confluence-research" "branch-impact-review")

for skill in "${SKILLS[@]}"; do
  SRC="$SCRIPT_DIR/$skill/SKILL.md"
  DEST_DIR="$SKILLS_DEST/$skill"
  DEST="$DEST_DIR/SKILL.md"

  if [[ ! -f "$SRC" ]]; then
    log "WARNING: $SRC not found, skipping"
    continue
  fi

  run mkdir -p "$DEST_DIR"

  # Replace hardcoded path with this machine's actual path
  REPLACED=$(sed "s|/Users/cuongvu/workspace/merchize/maintain/tools/confluence_fetch.py|$CONFLUENCE_TOOL|g" "$SRC")

  if $DRY_RUN; then
    echo "[dry-run] Would write $DEST (path replaced: $CONFLUENCE_TOOL)"
  else
    echo "$REPLACED" > "$DEST"
    log "Installed: $DEST"
  fi
done

echo ""
log "Done. Restart Claude Code (or open a new session) for skills to take effect."
