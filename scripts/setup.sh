#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
  echo "==> Criando ambiente virtual local"
  python3 -m venv --without-pip .venv || {
    echo "Não foi possível criar o ambiente virtual. No Ubuntu, instale python3-venv e tente novamente." >&2
    exit 1
  }
fi

if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  echo "==> Preparando pip dentro do ambiente virtual (sem alterar o Python do sistema)"
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl é necessário para preparar o ambiente Python." >&2
    exit 1
  fi
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$TMP_DIR/get-pip.py"
  .venv/bin/python "$TMP_DIR/get-pip.py"
fi

echo "==> Instalando dependências Python"
.venv/bin/python -m pip install -r requirements.txt
echo "==> Pronto. Para abrir o painel: bash scripts/start_admin.sh"
