#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c 'import bs4, httpx, jinja2, lxml, tldextract' >/dev/null 2>&1; then
  bash scripts/setup.sh
fi

exec .venv/bin/python -m siteaudit admin "$@"
