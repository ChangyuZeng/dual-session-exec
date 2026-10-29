#!/usr/bin/env sh
# 一键安装 dual-session-exec 到本机 agent 技能目录
# 用法：curl -fsSL https://raw.githubusercontent.com/ChangyuZeng/dual-session-exec/main/install.sh | sh
# 可选：DSE_DIR=/your/skills/dir 指定目标目录
set -e
REPO="https://github.com/ChangyuZeng/dual-session-exec"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$REPO/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP"
SRC="$TMP/dual-session-exec-main/dual-session-exec"

if [ -n "$DSE_DIR" ]; then
  TARGETS="$DSE_DIR"
else
  TARGETS="$HOME/.agents/skills"
  for d in "$HOME/.codex/skills" "$HOME/.claude/skills" "$HOME/.workbuddy/skills"; do
    [ -d "$d" ] && TARGETS="$TARGETS $d"
  done
fi

for t in $TARGETS; do
  mkdir -p "$t"
  if [ -e "$t/dual-session-exec" ]; then
    mv "$t/dual-session-exec" "$t/dual-session-exec.bak.$(date +%Y%m%d%H%M%S)"
  fi
  cp -R "$SRC" "$t/dual-session-exec"
  echo "installed -> $t/dual-session-exec"
done
