#!/usr/bin/env bash
# Install Claude Code skills (LOCAL / project-level) from this repo.
#
# Usage:
#   bash install.sh [--dry-run] <target_folder>
#
#   <target_folder>  Thư mục project gốc — skill sẽ được cài vào
#                    <target_folder>/.claude/skills/ (chỉ dùng được trong project đó).
#                    Bỏ trống => mặc định là workspace `maintain`
#                    (thư mục cha của confluence-skills/).
#
# Ví dụ:
#   bash install.sh                              # cài vào <maintain>/.claude/skills/
#   bash install.sh ~/workspace/merchize/maintain
#   bash install.sh --dry-run ./some-project
#
# Đường dẫn tới confluence_fetch.py được tự động resolve theo vị trí thực tế
# của repo này trên máy bạn (absolute path), nên hoạt động bất kể cwd.

set -euo pipefail

DRY_RUN=false
TARGET_ARG=""

# Parse args (cho phép --dry-run đứng trước hoặc sau target folder)
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) TARGET_ARG="$arg" ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # confluence-skills/skills
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"                     # confluence-skills
WORKSPACE_DIR="$(cd "$REPO_DIR/.." && pwd)"                  # maintain (mặc định)
CONFLUENCE_TOOL="$REPO_DIR/confluence_fetch.py"

# Chuỗi placeholder hardcoded trong các SKILL.md cần được thay thế
OLD_PATH="/Users/cuongvu/workspace/merchize/maintain/tools/confluence_fetch.py"

# Xác định thư mục đích
TARGET_DIR="${TARGET_ARG:-$WORKSPACE_DIR}"
if [[ ! -d "$TARGET_DIR" ]]; then
  echo "[install-skills] ERROR: target folder không tồn tại: $TARGET_DIR" >&2
  exit 1
fi
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"
SKILLS_DEST="$TARGET_DIR/.claude/skills"

log() { echo "[install-skills] $*"; }
run() {
  if $DRY_RUN; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

if [[ ! -f "$CONFLUENCE_TOOL" ]]; then
  log "WARNING: không tìm thấy $CONFLUENCE_TOOL — skill vẫn cài nhưng path sẽ sai"
fi

log "Repo            : $REPO_DIR"
log "Skills src      : $SCRIPT_DIR"
log "Target project  : $TARGET_DIR"
log "Skills dest     : $SKILLS_DEST"
log "Confluence tool : $CONFLUENCE_TOOL"
$DRY_RUN && log "(dry-run: không ghi file)"
echo ""

SKILLS=("confluence-research" "branch-impact-review" "break-task-executor")

for skill in "${SKILLS[@]}"; do
  SRC="$SCRIPT_DIR/$skill/SKILL.md"
  DEST_DIR="$SKILLS_DEST/$skill"
  DEST="$DEST_DIR/SKILL.md"

  if [[ ! -f "$SRC" ]]; then
    log "WARNING: $SRC not found, skipping"
    continue
  fi

  run mkdir -p "$DEST_DIR"

  # Thay placeholder path bằng đường dẫn thực tế trên máy này
  REPLACED=$(sed "s|$OLD_PATH|$CONFLUENCE_TOOL|g" "$SRC")

  if $DRY_RUN; then
    echo "[dry-run] Would write $DEST"
    echo "[dry-run]   CONFLUENCE_TOOL -> $CONFLUENCE_TOOL"
  else
    echo "$REPLACED" > "$DEST"
    log "Installed: $DEST"
  fi
done

echo ""
log "Done. Mở session Claude Code mới trong '$TARGET_DIR' để skill có hiệu lực."
