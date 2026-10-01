#!/usr/bin/env bash
# ===========================================================================
# Instala o navegador (Chromium) usado pelo siteaudit em sites em JavaScript
# e no scraping do Google Maps — SEM precisar de root/sudo.
#
#   bash scripts/install_browser.sh
#
# Se você TEM root, isto resolve tudo de uma vez:
#   pip install playwright && sudo playwright install-deps chromium && playwright install chromium
# ===========================================================================
set -euo pipefail

DEPS_DIR="${CHROMIUM_LIB_PATH:-$HOME/.local/lib/chromium-deps}"
mkdir -p "$DEPS_DIR"

echo "==> 1/3 Instalando o pacote Python do Playwright"
python3 -m pip install --quiet --upgrade playwright

if python3 -c "import playwright" 2>/dev/null; then
  echo "==> 2/3 Baixando o Chromium"
  python3 -m playwright install chromium
else
  echo "ERRO: não foi possível importar o playwright." >&2
  exit 1
fi

echo "==> 3/3 Garantindo as bibliotecas do sistema (modo sem root)"
if [ "$(id -u)" = "0" ]; then
  python3 -m playwright install-deps chromium || true
else
  # Baixa os .deb das dependências e extrai em $DEPS_DIR (não precisa de root).
  # O siteaudit adiciona esse diretório ao LD_LIBRARY_PATH automaticamente.
  if command -v apt-get >/dev/null 2>&1; then
    TMP="$(mktemp -d)"
    pushd "$TMP" >/dev/null
    for pkg in libnspr4 libnss3 libasound2 libasound2t64 libatk1.0-0 libatk1.0-0t64 \
               libatk-bridge2.0-0 libatk-bridge2.0-0t64 libatspi2.0-0 libatspi2.0-0t64 \
               libcups2 libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
               libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libxshmfence1 \
               libepoxy0 libwayland-client0 libxext6 libx11-6 libxcb1 libexpat1; do
      apt-get download "$pkg" >/dev/null 2>&1 && echo "    + $pkg" || true
    done
    # pacotes que mudaram de nome no Debian 13 / Ubuntu 24.04
    for missing in libnss3 libatk-bridge2.0-0t64; do
      if ! ls ./*.deb 2>/dev/null | grep -q "$missing"; then
        echo "    ! $missing não veio pelo apt-get — baixando direto do pool do Debian"
        case "$missing" in
          libnss3)
            curl -sL -o libnss3.deb \
              "$(curl -s http://deb.debian.org/debian/pool/main/n/nss/ \
                 | grep -o 'libnss3_[^"]*amd64.deb' | sort -V | tail -1 \
                 | sed 's|^|http://deb.debian.org/debian/pool/main/n/nss/|')" || true ;;
          libatk-bridge2.0-0t64)
            curl -sL -o libatk-bridge2.0-0t64.deb \
              "$(curl -s http://deb.debian.org/debian/pool/main/a/at-spi2-core/ \
                 | grep -o 'libatk-bridge2.0-0t64_[^"]*amd64.deb' | sort -V | tail -1 \
                 | sed 's|^|http://deb.debian.org/debian/pool/main/a/at-spi2-core/|')" || true ;;
        esac
      fi
    done
    for deb in ./*.deb; do
      [ -e "$deb" ] && dpkg-deb -x "$deb" "$DEPS_DIR" 2>/dev/null || true
    done
    popd >/dev/null
    rm -rf "$TMP"
    echo "    bibliotecas em: $DEPS_DIR"
  else
    echo "    (sem apt-get nesta máquina; se o Chromium não abrir, instale as dependências do sistema)"
  fi
fi

echo
echo "==> Verificando"
if CHROMIUM_LIB_PATH="$DEPS_DIR" python3 - "$DEPS_DIR" <<'PY'
import sys
from siteaudit.utils.http import Fetcher
Fetcher.ensure_chromium_libs()
f = Fetcher()
print("    Playwright disponível:", f.has_playwright())
try:
    f._ensure_browser()
    print("    Chromium: OK")
    f.close()
except Exception as exc:
    print("    Chromium falhou:", type(exc).__name__, str(exc)[:120])
    sys.exit(0)
PY
then :; fi
echo
echo "Pronto. Teste com:"
echo "  python3 -m siteaudit audit --url https://example.com --render --screenshots"
