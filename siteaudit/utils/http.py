"""Cliente HTTP do siteaudit.

Recursos:
  * pool de User-Agents realistas, retries e timeouts
  * rate limit por host (educado com os servidores alvo)
  * respeita robots.txt por padrão (use --ignore-robots em sites próprios/autorizados)
  * fallback para navegador real (Playwright/Chromium) em sites renderizados em JS
"""

from __future__ import annotations

import random
import re
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
]

HEADERS_BASE = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass
class FetchResult:
    url: str
    final_url: str = ""
    status_code: int = 0
    html: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    elapsed_ms: int = 0
    size_bytes: int = 0
    redirects: list[str] = field(default_factory=list)
    method: str = "http"     # http | browser
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status_code >= 200 and self.status_code < 400 and bool(self.html)


class Fetcher:
    """Cliente HTTP com cache de robots.txt e rate limiting por host."""

    def __init__(
        self,
        timeout: float = 20.0,
        delay: float = 0.6,
        respect_robots: bool = True,
        proxy: str | None = None,
        user_agent: str | None = None,
        max_retries: int = 2,
    ) -> None:
        self.timeout = timeout
        self.delay = delay
        self.respect_robots = respect_robots
        self.max_retries = max_retries
        self._ua = user_agent or random.choice(UA_POOL)
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}
        self._lock = threading.Lock()
        self._playwright = None
        self._browser = None
        transport_kwargs: dict[str, object] = {}
        if proxy:
            transport_kwargs["proxy"] = proxy
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={**HEADERS_BASE, "User-Agent": self._ua},
            **transport_kwargs,  # type: ignore[arg-type]
        )

    # ---------------------------------------------------------------- robots
    def robots_for(self, url: str) -> RobotFileParser | None:
        parts = urlparse(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root in self._robots:
            return self._robots[root]
        rp = RobotFileParser()
        try:
            r = self._client.get(root + "/robots.txt", timeout=8)
            if r.status_code >= 400:
                rp = None
            else:
                rp.parse(r.text.splitlines())
        except Exception:
            rp = None
        self._robots[root] = rp
        return rp

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        rp = self.robots_for(url)
        if rp is None:
            return True
        try:
            return rp.can_fetch(self._ua, url)
        except Exception:
            return True

    def sitemaps(self, url: str) -> list[str]:
        rp = self.robots_for(url)
        if not rp:
            return []
        try:
            return list(rp.site_maps() or [])
        except Exception:
            return []

    # ------------------------------------------------------------------ core
    def _throttle(self, host: str) -> None:
        with self._lock:
            last = self._last_hit.get(host, 0.0)
            wait = self.delay - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            self._last_hit[host] = time.time()

    def get(
        self, url: str, render: bool = False, timeout: float | None = None,
        respect_robots: bool = False,
    ) -> FetchResult:
        if respect_robots and not self.allowed(url):
            return FetchResult(url=url, error="robots.txt não permite esta página")
        host = urlparse(url).netloc
        self._throttle(host)
        if render:
            res = self.render(url, respect_robots=respect_robots)
            if res.ok:
                return res
        started = time.time()
        last_err = ""
        for attempt in range(self.max_retries + 1):
            try:
                r = self._client.get(url, timeout=timeout or self.timeout)
                elapsed = int((time.time() - started) * 1000)
                redirects = [str(h.headers.get("location", "")) for h in r.history]
                ctype = r.headers.get("content-type", "")
                html = ""
                if "text" in ctype or "html" in ctype or not ctype:
                    html = r.text
                return FetchResult(
                    url=url,
                    final_url=str(r.url),
                    status_code=r.status_code,
                    html=html,
                    headers=dict(r.headers),
                    elapsed_ms=elapsed,
                    size_bytes=len(r.content),
                    redirects=[x for x in redirects if x],
                )
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {exc}"
                time.sleep(0.6 * (attempt + 1))
        return FetchResult(url=url, error=last_err or "falha desconhecida")

    def head(self, url: str, respect_robots: bool = False) -> FetchResult:
        if respect_robots and not self.allowed(url):
            return FetchResult(url=url, error="robots.txt não permite este recurso")
        self._throttle(urlparse(url).netloc)
        started = time.time()
        try:
            r = self._client.head(url, timeout=self.timeout, follow_redirects=True)
            return FetchResult(
                url=url,
                final_url=str(r.url),
                status_code=r.status_code,
                headers=dict(r.headers),
                elapsed_ms=int((time.time() - started) * 1000),
                size_bytes=int(r.headers.get("content-length", 0) or 0),
            )
        except Exception as exc:  # noqa: BLE001
            return FetchResult(url=url, error=f"{type(exc).__name__}: {exc}")

    def text(self, url: str, respect_robots: bool = False) -> str:
        """Baixa um recurso de texto (CSS, robots, sitemap) sem parsear HTML."""
        if respect_robots and not self.allowed(url):
            return ""
        self._throttle(urlparse(url).netloc)
        try:
            r = self._client.get(url, timeout=self.timeout, follow_redirects=True)
            return r.text if r.status_code < 400 else ""
        except Exception:
            return ""

    # --------------------------------------------------------------- browser
    def has_playwright(self) -> bool:
        try:
            import playwright.sync_api  # noqa: F401
            return True
        except Exception:
            return False

    @staticmethod
    def ensure_chromium_libs() -> str:
        """Garante que as libs do Chromium entrem no LD_LIBRARY_PATH.

        Em ambientes sem root (containers, sandboxes) as dependências do Chromium
        podem estar em ~/.local/lib/chromium-deps — veja scripts/install_browser.sh.
        """
        import os
        from pathlib import Path

        extra = os.environ.get("CHROMIUM_LIB_PATH") or str(Path.home() / ".local/lib/chromium-deps")
        candidates = [f"{extra}/usr/lib/x86_64-linux-gnu", f"{extra}/lib/x86_64-linux-gnu", extra]
        existing = [c for c in candidates if Path(c).is_dir()]
        if not existing:
            return ""
        current = os.environ.get("LD_LIBRARY_PATH", "")
        missing = [c for c in existing if c not in current]
        if missing:
            os.environ["LD_LIBRARY_PATH"] = ":".join(missing + ([current] if current else []))
        return os.environ["LD_LIBRARY_PATH"]

    def _ensure_browser(self):
        if self._browser:
            return self._browser
        from playwright.sync_api import sync_playwright

        self.ensure_chromium_libs()

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        )
        return self._browser

    def render(
        self, url: str, wait_ms: int = 2500, screenshot: str | None = None,
        respect_robots: bool = False,
    ) -> FetchResult:
        """Carrega a página em Chromium real (necessário para sites em JS e Google Maps)."""
        if respect_robots and not self.allowed(url):
            return FetchResult(url=url, error="robots.txt não permite esta página")
        if not self.has_playwright():
            return FetchResult(url=url, error="Playwright não instalado (pip install playwright && playwright install chromium)")
        started = time.time()
        try:
            browser = self._ensure_browser()
            ctx = browser.new_context(
                user_agent=self._ua,
                locale="pt-BR",
                viewport={"width": 1440, "height": 900},
                timezone_id="America/Sao_Paulo",
            )
            page = ctx.new_page()
            resp = page.goto(url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
            try:
                page.wait_for_load_state("networkidle", timeout=wait_ms)
            except Exception:
                page.wait_for_timeout(wait_ms)
            html = page.content()
            status = resp.status if resp else 200
            final = page.url
            headers = resp.headers if resp else {}
            if screenshot:
                page.screenshot(path=screenshot, full_page=False)
            ctx.close()
            return FetchResult(
                url=url,
                final_url=final,
                status_code=status,
                html=html,
                headers=dict(headers) if headers else {},
                elapsed_ms=int((time.time() - started) * 1000),
                size_bytes=len(html.encode("utf-8", "ignore")),
                method="browser",
            )
        except Exception as exc:  # noqa: BLE001
            return FetchResult(url=url, error=f"render: {type(exc).__name__}: {exc}")

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
