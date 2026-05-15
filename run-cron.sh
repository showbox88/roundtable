#!/usr/bin/env bash
# Cron wrapper: discussion.py 跑一次，所有输出追加到 logs/cron.log
set -u
cd "$(dirname "$0")"
mkdir -p logs
{
  echo "=== $(date -Iseconds) start ==="
  .venv/bin/python discussion.py
  echo "=== $(date -Iseconds) exit=$? ==="
  echo
} >> logs/cron.log 2>&1
