"""Métricas de performance sem depender de laboratório externo.

Mede o que dá para medir de forma honesta em uma visita: peso da página,
quantidade de requisições, recursos bloqueantes, imagens pesadas,
terceiros e tempo de resposta do servidor.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..utils.text import absolutize, host_of, reg_domain

SLOW_ASSET_BYTES = 250_000     # 250 KB por imagem já é demais
HEAVY_PAGE_BYTES = 3_000_000   # 3 MB


def extract_perf(
    soup: BeautifulSoup,
    base_url: str,
    fetcher,
    elapsed_ms: int,
    html_bytes: int,
    deep: bool = True,
    fetch_method: str = "http",
) -> dict:
    scripts = soup.find_all("script", src=True)
    styles = soup.find_all("link", rel=lambda v: v and "stylesheet" in str(v).lower())
    imgs = soup.find_all("img")
    iframes = soup.find_all("iframe")
    fonts = soup.find_all("link", href=re.compile(r"\.(woff2?|ttf|otf|eot)"))

    head = soup.head or soup
    blocking = []
    for s in scripts:
        if s.get("defer") or s.get("async") or s.get("type") == "module":
            continue
        blocking.append(absolutize(s.get("src", ""), base_url))
    blocking_styles = [absolutize(t.get("href", ""), base_url) for t in styles]

    third_party: set[str] = set()
    for tag in list(scripts) + list(styles) + list(iframes) + list(imgs):
        url = absolutize(tag.get("src") or tag.get("href") or "", base_url)
        if url.startswith("http") and reg_domain(url) and reg_domain(url) != reg_domain(base_url):
            third_party.add(reg_domain(url))

    lazy = sum(1 for i in imgs if i.get("loading") == "lazy")
    no_dimensions = sum(1 for i in imgs if not i.get("width") or not i.get("height"))

    # tamanho real dos assets (HEAD limitado para não abusar do alvo)
    asset_bytes = 0
    heavy_assets: list[dict] = []
    measured = 0
    if deep and fetcher:
        candidates = [absolutize(t.get("src") or t.get("href") or "", base_url)
                      for t in list(scripts)[:6] + list(styles)[:4] + list(imgs)[:12]]
        for url in candidates:
            if not url.startswith("http") or measured >= 20:
                continue
            res = fetcher.head(url, respect_robots=True)
            if res.status_code == 200 and res.size_bytes:
                asset_bytes += res.size_bytes
                measured += 1
                if res.size_bytes > SLOW_ASSET_BYTES:
                    heavy_assets.append({"url": url, "kb": round(res.size_bytes / 1024)})
            elif res.status_code == 0:
                continue
    total_bytes = html_bytes + asset_bytes
    estimated = total_bytes if measured else html_bytes

    preloads = len(soup.find_all("link", rel=lambda v: v and "preload" in str(v).lower()))
    preconnects = len(soup.find_all("link", rel=lambda v: v and "preconnect" in str(v).lower()))
    inline_scripts = len(soup.find_all("script", src=False))
    inline_styles = len(soup.find_all("style"))

    perf = {
        # Fetcher measures until the response body is received (or browser
        # rendering completes); it does not expose a true time-to-first-byte.
        "response_duration_ms": elapsed_ms,
        "measurement_method": fetch_method,
        "html_kb": round(html_bytes / 1024, 1),
        "asset_kb_measured": round(asset_bytes / 1024, 1),
        "estimated_page_kb": round(estimated / 1024, 1),
        "requests_scripts": len(scripts),
        "requests_styles": len(styles),
        "requests_images": len(imgs),
        "requests_iframes": len(iframes),
        "requests_fonts": len(fonts),
        "requests_total_estimate": len(scripts) + len(styles) + len(imgs) + len(iframes) + len(fonts),
        "render_blocking_scripts": blocking[:10],
        "render_blocking_count": len(blocking) + len(blocking_styles),
        "third_party_domains": sorted(third_party)[:15],
        "third_party_count": len(third_party),
        "images_lazy": lazy,
        "images_without_dimensions": no_dimensions,
        "heavy_assets": heavy_assets[:10],
        "preload_hints": preloads,
        "preconnect_hints": preconnects,
        "inline_scripts": inline_scripts,
        "inline_styles": inline_styles,
        "http2": bool(re.search(r"HTTP/2|HTTP/3", str((getattr(fetcher, "_client", None) and "") or ""))),
    }
    perf["perf_grade"] = _grade(perf)
    return perf


def _grade(perf: dict) -> str:
    score = 100
    if perf.get("measurement_method", "http") == "http" and perf["response_duration_ms"] > 1500:
        score -= 25
    elif perf.get("measurement_method", "http") == "http" and perf["response_duration_ms"] > 800:
        score -= 12
    if perf["estimated_page_kb"] > HEAVY_PAGE_BYTES / 1024:
        score -= 25
    elif perf["estimated_page_kb"] > 1500:
        score -= 12
    if perf["render_blocking_count"] > 6:
        score -= 15
    elif perf["render_blocking_count"] > 3:
        score -= 7
    if perf["requests_total_estimate"] > 80:
        score -= 12
    elif perf["requests_total_estimate"] > 45:
        score -= 6
    if perf["third_party_count"] > 8:
        score -= 8
    score = max(0, min(100, score))
    return ("A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60
            else "D" if score >= 45 else "E")


def perf_issues(perf: dict) -> list[dict]:
    issues: list[dict] = []

    def add(severity, title, detail, fix, impact=""):
        issues.append({"severity": severity, "category": "Performance", "title": title,
                       "detail": detail, "fix": fix, "impact": impact})

    if perf.get("measurement_method", "http") == "http" and perf["response_duration_ms"] > 1500:
        add("critico", f"Resposta HTTP demorou {perf['response_duration_ms']} ms",
            "A duração inclui a transferência da resposta; não é uma medição isolada de TTFB.",
            "Hospedagem com cache + CDN + imagens otimizadas.",
            "Cada segundo a mais derruba a conversão — e o Google rebaixa.")
    elif perf.get("measurement_method", "http") == "http" and perf["response_duration_ms"] > 800:
        add("medio", f"Resposta HTTP demorou {perf['response_duration_ms']} ms",
            "Duração da requisição e transferência acima de 800 ms; não equivale ao TTFB.",
            "Cache de página + CDN.")

    if perf["estimated_page_kb"] > HEAVY_PAGE_BYTES / 1024:
        add("alto", f"Página pesada (~{perf['estimated_page_kb']} KB)",
            "Consome dados do visitante e demora para abrir no 4G.",
            "Otimizar imagens (WebP/AVIF), lazy load e minificação.")

    if perf["render_blocking_count"] > 3:
        add("alto", f"{perf['render_blocking_count']} recursos bloqueiam o carregamento",
            "Scripts e CSS no <head> atrasam a primeira pintura.",
            "defer/async nos scripts, CSS crítico inline, pré-carregar fontes.")

    if perf["heavy_assets"]:
        pior = max(perf["heavy_assets"], key=lambda a: a["kb"])
        add("alto", f"{len(perf['heavy_assets'])} arquivos acima de 250 KB (o maior tem {pior['kb']} KB)",
            pior["url"][:120], "Redimensionar para o tamanho real de exibição e converter para WebP.")

    imgs = perf["requests_images"]
    if imgs and perf["images_lazy"] / max(imgs, 1) < 0.5:
        add("medio", f"{imgs - perf['images_lazy']} imagens sem lazy loading",
            "Todas as imagens são baixadas de uma vez, mesmo as que estão fora da tela.",
            "loading='lazy' + width/height para evitar layout shift.")

    if perf["third_party_count"] > 8:
        add("baixo", f"{perf['third_party_count']} domínios de terceiros",
            ", ".join(perf["third_party_domains"][:8]),
            "Reduzir scripts de terceiros (pixels, chats, widgets).")

    if perf["preconnect_hints"] == 0 and perf["third_party_count"] > 2:
        add("baixo", "Sem preconnect/dns-prefetch", "Cada domínio de terceiro adiciona latência de DNS/TLS.",
            "<link rel='preconnect'> nos domínios críticos.")

    return issues
