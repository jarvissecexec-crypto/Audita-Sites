"""Provedores de busca web: DuckDuckGo e Bing.

São os provedores "sem chave de API". O Google Maps (scraping) e a Places API
ficam em arquivos separados por precisarem de navegador / credencial.
"""

from __future__ import annotations

import base64
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from ..models import Lead
from ..utils.text import extract_phones, norm_ws
from .base import BaseProvider, clean_website, reg_domain

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")


def decode_bing_url(href: str) -> str:
    """Bing encapsula o destino em /ck/a?u=a1<base64>."""
    if "bing.com/ck/a" not in (href or ""):
        return href or ""
    token = parse_qs(urlparse(href).query).get("u", [""])[0]
    if token.startswith("a1"):
        try:
            return base64.urlsafe_b64decode(token[2:] + "==").decode("utf-8", "ignore").strip()
        except Exception:
            return href
    return href


def looks_relevant(query: str, name: str, url: str, snippet: str) -> bool:
    """Bloqueia SERP envenenada: exige que o resultado tenha relação real com a busca."""
    import unicodedata

    def norm(t: str) -> str:
        t = unicodedata.normalize("NFD", (t or "").lower())
        return "".join(c for c in t if unicodedata.category(c) != "Mn")

    q = norm(query)
    terms = [t for t in re.split(r"[^a-z0-9]+", q) if len(t) > 2]
    if not terms:
        return True
    hay = " ".join([norm(name), norm(url), norm(snippet)])
    hits = sum(1 for t in terms if t in hay)
    return hits >= max(1, len(terms) // 2)


class DuckDuckGoProvider(BaseProvider):
    """Usa o endpoint HTML do DuckDuckGo (gratuito, sem chave)."""

    name = "ddg"
    label = "DuckDuckGo"

    def search(self, query: str, limit: int = 20) -> list[Lead]:
        leads: list[Lead] = []
        encoded = re.sub(r"\s+", "+", query)
        res = None
        soup = None
        for endpoint in ("https://html.duckduckgo.com/html/", "https://lite.duckduckgo.com/lite/",
                         "https://html.duckduckgo.com/html/"):
            url = f"{endpoint}?q={encoded}&kl=br-pt"
            res = self.fetcher.get(url)
            soup = BeautifulSoup(res.html or "", "lxml")
            if soup.find("a", href=re.compile(r"^https?://")) and "anomaly" not in (res.html or "").lower():
                break
            time.sleep(2.5)  # anti-bot: espera antes de tentar de novo
        if soup is None or not soup.find("a") or "anomaly" in ((res.html if res else "") or "").lower():
            self.errors.append("ddg: resposta bloqueada (anti-bot) nesta rodada — tente --providers bing,maps")
            return leads

        for node in soup.select("a.result__a, a.result-link, table a[href^='http']"):
            href = node.get("href", "")
            if "uddg=" in href:
                href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
            title = norm_ws(node.get_text(" "))
            if not href.startswith("http") or "duckduckgo.com" in href:
                continue
            snippet_node = node.find_parent(["div", "tr", "li"])
            snippet = norm_ws(snippet_node.get_text(" "))[:400] if snippet_node else ""
            lead = Lead(
                name=title.split(" | ")[0].split(" – ")[0].split(" - ")[0][:90],
                website=clean_website(href),
                address=snippet,
                category=query,
            )
            phones = extract_phones(snippet)
            if phones:
                lead.phone = phones[0]
            leads.append(lead)
            if len(leads) >= limit:
                break
        return leads


class BingProvider(BaseProvider):
    """Busca web do Bing (pt-BR). Boa cobertura de empresas locais."""

    name = "bing"
    label = "Bing"

    def search(self, query: str, limit: int = 20) -> list[Lead]:
        leads: list[Lead] = []
        page = 1
        while len(leads) < limit and page <= 3:
            url = (
                "https://www.bing.com/search?q=" + re.sub(r"\s+", "+", query)
                + f"&mkt=pt-BR&setmkt=pt-BR&setlang=pt-BR&cc=BR&count=30&first={(page - 1) * 30 + 1}"
            )
            res = self.fetcher.get(url)
            soup = BeautifulSoup(res.html or "", "lxml")
            items = soup.select("li.b_algo")
            if not items:
                if page == 1:
                    self.errors.append("bing: nenhum resultado (possível bloqueio)")
                break
            for item in items:
                a = item.select_one("h2 a")
                if not a:
                    continue
                href = decode_bing_url(a.get("href", ""))
                title = norm_ws(a.get_text(" "))
                body = norm_ws(item.get_text(" "))
                if not looks_relevant(query, title, href, body):
                    continue
                lead = Lead(
                    name=title.split(" | ")[0].split(" – ")[0].split(" - ")[0][:90],
                    website=clean_website(href),
                    address=body[:400],
                    category=query,
                )
                phones = extract_phones(body)
                if phones:
                    lead.phone = phones[0]
                if lead.website or lead.phone:
                    leads.append(lead)
                if len(leads) >= limit:
                    break
            page += 1
            time.sleep(self.delay)
        return leads


class GoogleWebProvider(BaseProvider):
    """Busca web do Google via navegador real (best-effort — pode cair em CAPTCHA)."""

    name = "google"
    label = "Google (navegador)"
    needs_browser = True

    def search(self, query: str, limit: int = 20) -> list[Lead]:
        if not self.fetcher.has_playwright():
            self.errors.append("google: requer Playwright (pip install playwright && playwright install chromium)")
            return []
        from playwright.sync_api import sync_playwright

        leads: list[Lead] = []
        url = "https://www.google.com/search?hl=pt-BR&gl=br&num=30&q=" + re.sub(r"\s+", "+", query)
        res = self.fetcher.render(url, wait_ms=2500)
        if not res.ok:
            self.errors.append(f"google: {res.error}")
            return leads
        soup = BeautifulSoup(res.html, "lxml")
        for node in soup.select("div.MjjYud, div.g, div.tF2Cxc"):
            a = node.select_one("a[href^='http'], a[href^='/url']")
            h3 = node.select_one("h3")
            if not (a and h3):
                continue
            href = a.get("href", "")
            if href.startswith("/url?") and "url=" in href:
                href = unquote(parse_qs(urlparse(href).query).get("url", [""])[0])
            title = norm_ws(h3.get_text(" "))
            body = norm_ws(node.get_text(" "))
            lead = Lead(
                name=title[:90],
                website=clean_website(href),
                address=body[:400],
                category=query,
            )
            phones = extract_phones(body)
            if phones:
                lead.phone = phones[0]
            leads.append(lead)
            if len(leads) >= limit:
                break
        if not leads:
            self.errors.append("google: 0 resultados (possível CAPTCHA/consent — prefira --providers bing,maps)")
        return leads
