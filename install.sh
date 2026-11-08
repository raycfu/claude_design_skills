#!/usr/bin/env bash
# One-command install for Ray's Claude video kit (github.com/raycfu/claude_design_skills).
# Installs: effects (51 effects) and reel-builder.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILLS="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$SKILLS"

copy_skill() {  # copy_skill <folder-in-this-repo> <skill-name>
  local src="$HERE/$1" dst="$SKILLS/$2"
  if [ -d "$dst" ] && [ ! -f "$dst/.raycfu" ]; then
    echo "Backing up your existing $2 skill to $dst.backup"
    rm -rf "$dst.backup"; mv "$dst" "$dst.backup"
  fi
  mkdir -p "$dst"
  (cd "$src" && tar --exclude=.venv --exclude=__pycache__ -cf - .) | (cd "$dst" && tar -xf -)
  touch "$dst/.raycfu"
  echo "Installed $2 -> $dst"
}

copy_skill effects effects
copy_skill reel-builder reel-builder

echo "Setting up the effects environment (first time takes about 2 minutes)..."
bash "$SKILLS/effects/scripts/setup.sh" || echo "Run it again after fixing the line above: bash $SKILLS/effects/scripts/setup.sh"
echo
echo "Done. Restart Claude Code, drop in a clip and type /effects or /reel-builder."
