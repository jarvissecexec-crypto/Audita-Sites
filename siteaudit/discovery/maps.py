"""Descoberta de empresas via Google Maps.

Duas rotas:

* ``maps``   — scraping com navegador real (sem custo, mas frágil: o Google pode
               exigir CAPTCHA a qualquer momento e os seletores mudam).
* ``places`` — Places API oficial (recomendado para uso comercial; precisa de
               chave em GOOGLE_MAPS_API_KEY ou --places-key).

Ambos entregam nome, telefone, endereço, nota, nº de avaliações, site e link do Maps.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ..models import Lead
from ..utils.text import extract_phones, normalize_phone, norm_ws
from .base import BaseProvider, clean_website, country_code


class MapsScraperProvider(BaseProvider):
    """Raspa a lista de resultados do Google Maps com Playwright.

    Para cada cartão: abre o painel de detalhes e lê website / telefone / endereço.
    """

    name = "maps"
    label = "Google Maps (scraping)"
    needs_browser = True
    max_attempts = 2

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_signature: tuple[str, str, str] = ("", "", "")

    def search(self, query: str, limit: int = 20) -> list[Lead]:
        if not self.fetcher.has_playwright():
            self.errors.append("maps: requer Playwright (pip install playwright && playwright install chromium)")
            return []
        from urllib.parse import quote_plus

        leads: list[Lead] = []
        code = country_code(self.country) or "br"
        language = "pt-BR" if code == "br" else "en"
        url = "https://www.google.com/maps/search/" + quote_plus(query) + f"/?hl={language}&gl={code}"
        last_error = ""
        for attempt in range(1, self.max_attempts + 1):
            try:
                leads = self._collect(page_url=url, limit=limit, query=query)  # noqa: F821
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {str(exc)[:120]}"
                leads = []
            if leads:
                break
            if attempt < self.max_attempts:
                time.sleep(3 * attempt)  # backoff: o Maps costuma liberar na 2ª tentativa
        if not leads and last_error and not self.errors:
            self.errors.append(f"maps: {last_error}")
        time.sleep(self.delay)
        return leads

    @staticmethod
    def _cards(page) -> list:
        """Tenta vários seletores para a lista de resultados (o layout muda)."""
        for selector in (
            'div[role="feed"] a[href*="/maps/place/"]',
            'a[href*="/maps/place/"]',
            'div[role="feed"] > div > div > a',
        ):
            found = page.query_selector_all(selector)
            if found:
                return found
        return []

    @staticmethod
    def _handle_consent(page) -> None:
        """Aceita o banner de consentimento do Google quando ele aparece."""
        for label in ("Aceitar tudo", "Accept all", "Concordo", "I agree", "Rejeitar tudo"):
            try:
                page.click(f"button:has-text('{label}')", timeout=1500)
                page.wait_for_timeout(1200)
                return
            except Exception:
                continue

    def _collect(self, page_url: str, limit: int, query: str) -> list[Lead]:
        """Carrega a lista, guarda os links e abre cada estabelecimento."""
        leads: list[Lead] = []
        self._last_signature = ("", "", "")
        browser = self.fetcher._ensure_browser()
        ctx = browser.new_context(
            user_agent=self.fetcher._ua,
            locale="pt-BR",
            viewport={"width": 1440, "height": 1000},
            timezone_id="America/Sao_Paulo",
        )
        page = ctx.new_page()
        page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        self._handle_consent(page)
        try:
            page.wait_for_selector('div[role="feed"]', timeout=20000)
        except Exception:
            page.wait_for_timeout(5000)

        # 1) rola a lista e guarda os links (href -> nome do cartão)
        feed = page.query_selector('div[role="feed"]')
        cards: list = []
        target = min(limit, 40)
        for _ in range(8):
            cards = self._cards(page)
            if len(cards) >= target:
                break
            if feed:
                try:
                    feed.evaluate("el => el.scrollTop = el.scrollHeight")
                    page.mouse.wheel(0, 4000)
                except Exception:
                    pass
            page.wait_for_timeout(1400)

        seen: set[str] = set()
        targets: list[tuple[str, str]] = []
        for card in cards:
            href = card.get_attribute("href") or ""
            if not href or "/maps/place/" not in href or href in seen:
                continue
            seen.add(href)
            targets.append((href, norm_ws(card.get_attribute("aria-label") or "")))
            if len(targets) >= limit:
                break

        if not targets:
            self.errors.append("maps: lista de resultados não carregou (CAPTCHA, bloqueio ou layout novo)")
            ctx.close()
            return leads

        # 2) abre cada estabelecimento pela própria URL (bem mais confiável)
        for href, fallback_name in targets:
            lead = self._read_place(page, href, fallback_name, query)
            if lead.name or lead.website or lead.phone:
                leads.append(lead)
            time.sleep(max(0.8, self.delay))

        ctx.close()
        return leads

    # --------------------------------------------- leitura direta do lugar
    def _read_place(self, page, href: str, fallback_name: str, query: str) -> Lead:
        """Abre a URL do estabelecimento e lê o painel de detalhes.

        Navegar direto para /maps/place/... é bem mais confiável do que clicar
        no cartão da lista (o painel às vezes não troca de empresa).
        """
        url = href if href.startswith("http") else "https://www.google.com" + href
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"maps: {type(exc).__name__}: {str(exc)[:80]}")
            return Lead(name=fallback_name, category=query, maps_url=href)
        try:
            page.wait_for_selector('div[role="main"] h1, div[role="main"] button[data-item-id^="phone"]',
                                   timeout=12000)
        except Exception:
            pass
        page.wait_for_timeout(900)

        soup = BeautifulSoup(page.content(), "lxml")
        panel = soup.select_one('div[role="main"]') or soup

        # --- nome
        name = ""
        for selector in ('h1.DUwDvf', 'h1'):
            el = panel.select_one(selector)
            if el:
                candidate = norm_ws(el.get_text(" "))
                if candidate and candidate.lower() not in ("resultados", "results", "google maps"):
                    name = candidate
                    break

        # --- site próprio
        website = ""
        a = panel.select_one('a[data-item-id="authority"]')
        if a:
            website = clean_website(a.get("href", ""))

        # --- telefone
        phone = ""
        btn = panel.select_one('button[data-item-id^="phone:tel:"]')
        if btn:
            found = extract_phones((btn.get("aria-label") or "") + " " + btn.get_text(" "))
            if found:
                phone = found[0]

        # --- endereço
        address = ""
        addr_btn = panel.select_one('button[data-item-id="address"]')
        if addr_btn:
            address = norm_ws((addr_btn.get("aria-label") or addr_btn.get_text(" ")).replace("Endereço: ", ""))

        # --- categoria
        category = ""
        for selector in ('button[jsaction*="category"]', '[data-item-id="category"]'):
            el = panel.select_one(selector)
            if el:
                category = norm_ws(el.get_text(" "))
                break

        # --- nota e avaliações (do painel)
        panel_text = ""
        try:
            panel_el = page.query_selector('div[role="main"]')
            if panel_el:
                panel_text = panel_el.inner_text()
        except Exception:
            pass
        rating, reviews = self._rating(None, panel, panel_text)

        return Lead(
            name=name[:120] or fallback_name[:120],
            website=website,
            phone=phone,
            address=address,
            category=category or query,
            rating=rating,
            reviews=reviews,
            maps_url=href,
        )

    @staticmethod
    def _rating(card, panel, panel_text: str = "") -> tuple[float | None, int | None]:  # noqa: C901
        """Nota e nº de avaliações.

        Ordem: texto do cartão na lista  ->  painel de detalhes.
        """
        rating = reviews = None

        def parse(text: str) -> tuple[float | None, int | None]:
            r = rv = None
            t = (text or "").replace("\u00a0", " ")
            m = re.search(r"(\d[.,]\d?)\s*[\(\n]\s*([\d.]+)\s*\)?", t)
            if m:
                try:
                    r = float(m.group(1).replace(",", "."))
                except ValueError:
                    r = None
                rv = int(re.sub(r"\D", "", m.group(2)) or 0) or None
            if r is None:
                m1 = re.search(r"(\d[.,]\d?)\s*(?:estrelas?|★)", t, re.I)
                if m1:
                    try:
                        r = float(m1.group(1).replace(",", "."))
                    except ValueError:
                        pass
            if rv is None:
                m2 = re.search(r"([\d.]+)\s*avalia", t, re.I)
                if m2:
                    rv = int(re.sub(r"\D", "", m2.group(1)) or 0) or None
            return r, rv

        card_text = ""
        if card is not None:
            try:
                card_text = card.inner_text()
            except Exception:
                card_text = card.get_attribute("aria-label") or ""
        rating, reviews = parse(card_text)

        if rating is None or reviews is None:
            p_rating, p_reviews = parse(panel_text or (panel.get_text(" ") if panel else ""))
            rating = rating if rating is not None else p_rating
            reviews = reviews if reviews is not None else p_reviews

        if rating is not None and not (0 <= rating <= 5):
            rating = None
        return rating, reviews


class PlacesApiProvider(BaseProvider):
    """Google Places API (Text Search + Details). Rota oficial e estável."""

    name = "places"
    label = "Google Places API"
    needs_api_key = True

    SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
    DETAIL_FIELDS = (
        "name,website,formatted_phone_number,international_phone_number,formatted_address,"
        "rating,user_ratings_total,url,types,opening_hours,address_components,business_status"
    )

    def search(self, query: str, limit: int = 20) -> list[Lead]:
        if not self.api_key:
            self.errors.append("places: defina GOOGLE_MAPS_API_KEY ou --places-key")
            return []
        leads: list[Lead] = []
        token = None
        while len(leads) < limit:
            code = country_code(self.country) or "br"
            language = "pt-BR" if code == "br" else "en"
            params = {"query": query, "key": self.api_key, "language": language, "region": code}
            if token:
                params["pagetoken"] = token
            url = self.SEARCH_URL + "?" + "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
            raw = self.fetcher.text(url)
            if not raw:
                break
            try:
                data = json.loads(raw)
            except Exception:
                self.errors.append("places: resposta inválida")
                break
            status = data.get("status")
            if status not in ("OK", "ZERO_RESULTS"):
                self.errors.append(f"places: status={status} {data.get('error_message', '')}".strip())
                break
            for item in data.get("results", []):
                lead = self._details(item.get("place_id", "")) if item.get("place_id") else Lead()
                if not lead.name:
                    lead.name = item.get("name", "")
                lead.category = (item.get("types") or [""])[0].replace("_", " ")
                lead.rating = item.get("rating")
                lead.reviews = item.get("user_ratings_total")
                lead.maps_url = f"https://www.google.com/maps/place/?q=place_id:{item.get('place_id', '')}"
                if not lead.address:
                    lead.address = item.get("formatted_address", "")
                if not lead.website:
                    lead.website = clean_website(item.get("website") or "")
                if not lead.phone:
                    lead.phone = normalize_phone(item.get("formatted_phone_number") or "")
                leads.append(lead)
                if len(leads) >= limit:
                    break
            token = data.get("next_page_token")
            if not token:
                break
            time.sleep(2.2)  # a API exige espera antes de usar o next_page_token
        return leads

    def _details(self, place_id: str) -> Lead:
        params = {
            "place_id": place_id,
            "fields": self.DETAIL_FIELDS,
            "key": self.api_key or "",
            "language": "pt-BR" if (country_code(self.country) or "br") == "br" else "en",
        }
        url = self.DETAILS_URL + "?" + "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
        raw = self.fetcher.text(url)
        lead = Lead()
        if not raw:
            return lead
        try:
            result = json.loads(raw).get("result", {})
        except Exception:
            return lead
        lead.name = result.get("name", "")
        lead.website = clean_website(result.get("website") or "")
        lead.phone = normalize_phone(result.get("formatted_phone_number") or result.get("international_phone_number") or "")
        lead.address = result.get("formatted_address", "")
        lead.rating = result.get("rating")
        lead.reviews = result.get("user_ratings_total")
        for comp in result.get("address_components", []):
            types = comp.get("types", [])
            if "administrative_area_level_2" in types:
                lead.city = comp.get("long_name", "")
            elif "administrative_area_level_1" in types:
                lead.state = comp.get("short_name", "")
        return lead
