"""Contrato comum dos provedores de descoberta."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from urllib.parse import quote_plus, urlparse

from ..models import Lead
from ..utils.http import Fetcher

# Domínios que NÃO são site próprio da empresa (redes sociais, diretórios, marketplaces).
# Um lead cujo único URL é um destes não teve site próprio localizado nas fontes.
NON_OWNED_DOMAINS = {
    "facebook.com", "m.facebook.com", "fb.com", "instagram.com", "linkedin.com",
    "youtube.com", "youtu.be", "wa.me", "api.whatsapp.com", "tiktok.com",
    "twitter.com", "x.com", "pinterest.com", "threads.net",
    "google.com", "maps.google.com", "goo.gl", "maps.app.goo.gl", "g.page",
    "wikipedia.org", "blogspot.com", "wordpress.com", "wix.com", "wixsite.com",
    "sites.google.com", "weebly.com", "yolasite.com", "webnode.com",
    # diretórios / agregadores brasileiros
    "guiamais.com.br", "guiadoinvestidor.com", "yellowpages.com.br", "paginasamarelas.com.br",
    "telelistas.net", "cyberpagens.com.br", "apontador.com.br", "encontracorreios.com.br",
    "tripadvisor.com.br", "tripadvisor.com", "yelp.com", "foursquare.com",
    "ifood.com.br", "rappi.com.br", "booking.com", "airbnb.com.br", "airbnb.com",
    "mercadolivre.com.br", "mercadolibre.com", "olist.com", "econodata.com.br",
    "cnpj.biz", "cnae.net", "consultacnpj.com", "casadosdados.com.br",
    "hotmart.com", "sympla.com.br", "eventbrite.com.br", "eventbrite.com",
    "justdial.com", "olx.com.br", "webcasas.com.br", "vivareal.com.br",
    "restaurantguru.com.br", "restaurantguru.com", "listamais.com.br", "solutudo.com.br",
    "guiatelefone.com", "telelistas.net", "portaldacidade.com", "portaldosmunicipios.com.br",
    "cidade-brasil.com.br", "ibge.gov.br", "econodata.com.br", "casadosdados.com.br",
    "infocnpj.com", "consultasocio.com", "cnpj.info", "ratoweb.com", "ondeir.com.br",
    "melhoresdestinos.com.br", "vivalocal.com", "acheiaqui.com.br", "encontrar.com.br",
    "brasil-infos.com", "brasilinfos.com", "benditoguia.com.br", "guiadoinvestidor.com", "melhorenvio.com",
}

# Fragmentos que indicam diretório/lista (não são site da empresa)
DIRECTORY_HINTS = (
    "restaurantguru", "tripadvisor", "yelp", "foursquare", "listamais", "solutudo",
    "guiatelefone", "telelistas", "paginasamarelas", "guiamais", "portaldacidade",
    "cidade-brasil", "econodata", "casadosdados", "infocnpj", "consultasocio",
    "wikimapia", "mapcarta", "nomadlist", "restaurant", "wheree", "tupalo",
)

# Títulos que indicam página de listagem, não empresa individual
LISTING_TITLE_RE = __import__("re").compile(
    r"(melhores?|os\s+\d+\s|top\s*\d|\d+\s+melhores?|lista|listas|ranking|"
    r"guia\s+(de|completo)|onde\s+(comer|encontrar|ir)|catálogo|catalogo|classificados|"
    r"(pizzarias|empresas|restaurantes|lojas|clínicas|clinicas|contadores|advogados|"
    r"imobiliárias|imobiliarias|academias|salões|saloes|oficinas|hotéis|hoteis)\s+em|"
    r"endereços?|telefones?\s+de|avaliad[oa]s?|como\s+escolher|\bvs\b)",
    __import__("re").I,
)

# Marcadores de "tem site próprio, mesmo que em construção"
OWNED_SUFFIX_HINTS = (".com.br", ".com", ".net", ".org", ".app", ".store", ".online", ".site", ".io")

COUNTRY_CODES = {
    "brasil": "br", "brazil": "br", "portugal": "pt", "argentina": "ar",
    "uruguai": "uy", "uruguay": "uy", "chile": "cl", "paraguai": "py",
    "paraguay": "py", "estados unidos": "us", "united states": "us", "canada": "ca",
    "canadá": "ca", "méxico": "mx", "mexico": "mx", "espanha": "es", "spain": "es",
    "reino unido": "gb", "united kingdom": "gb", "frança": "fr", "france": "fr",
    "alemanha": "de", "germany": "de", "italia": "it", "itália": "it",
}


def country_code(country: str) -> str:
    """Resolve países comuns e aceita códigos ISO alfa-2 fornecidos pelo usuário."""
    value = (country or "").strip().casefold()
    if re.fullmatch(r"[a-zA-Z]{2}", value):
        return value.lower()
    return COUNTRY_CODES.get(value, "")


def reg_domain(url: str) -> str:
    try:
        import tldextract
        ext = tldextract.extract(url or "")
        return ".".join(p for p in (ext.domain, ext.suffix) if p)
    except Exception:
        return urlparse(url or "").netloc.lower().removeprefix("www.")


def is_directory_domain(url: str) -> bool:
    """Diretórios, agregadores e portais não são site próprio da empresa."""
    domain = reg_domain(url or "")
    if not domain:
        return True
    if domain in NON_OWNED_DOMAINS:
        return True
    return any(hint in domain for hint in DIRECTORY_HINTS)


def looks_like_listing(name: str) -> bool:
    """Detecta títulos de página de listagem ('5 melhores pizzarias em...')."""
    return bool(LISTING_TITLE_RE.search(name or ""))


def clean_website(url: str | None) -> str:
    """Normaliza a URL do site da empresa ou devolve '' quando não é site próprio."""
    if not url:
        return ""
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u.lstrip("/")
    if is_directory_domain(u):
        return ""
    parsed = urlparse(u)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}" or ""


def is_social_or_directory(url: str) -> bool:
    return reg_domain(url or "") in NON_OWNED_DOMAINS


def normalize_lead(lead: Lead) -> Lead:
    lead.name = re.sub(r"\s+", " ", (lead.name or "")).strip()
    # título de listagem nunca é nome de empresa
    if looks_like_listing(lead.name) and not lead.phone and not lead.maps_url:
        lead.name = ""
    lead.website = clean_website(lead.website)
    lead.has_website = bool(lead.website)
    if not lead.has_website:
        lead.status = "website_not_located"
    return lead


def dedupe(leads: list[Lead]) -> list[Lead]:
    """Remove duplicatas por domínio (prioriza quem tem mais dados) ou por nome+telefone."""
    by_domain: dict[str, Lead] = {}
    out: list[Lead] = []
    for lead in leads:
        key = reg_domain(lead.website) if lead.website else ""
        if not key:
            key = "name:" + (lead.name or "").lower()
        if key in by_domain:
            cur = by_domain[key]
            merged = merge_lead(cur, lead)
            by_domain[key] = merged
            out[out.index(cur)] = merged
            continue
        by_domain[key] = lead
        out.append(lead)
    return out


def merge_lead(a: Lead, b: Lead) -> Lead:
    """Preenche lacunas do lead `a` com dados do lead `b`."""
    for field in ("name", "website", "phone", "address", "city", "state", "category", "maps_url"):
        if not getattr(a, field) and getattr(b, field):
            setattr(a, field, getattr(b, field))
    if a.rating is None:
        a.rating = b.rating
    if a.reviews is None:
        a.reviews = b.reviews
    a.has_website = bool(a.website)
    if a.source != b.source:
        sources = []
        for token in (a.source + "+" + b.source).split("+"):
            token = token.strip()
            if token and token not in sources:
                sources.append(token)
        a.source = "+".join(sources)
    return a


def build_queries(
    niche: str, city: str, state: str, extra: list[str] | None = None, country: str = "",
) -> list[str]:
    """Monta as consultas de busca a partir de nicho + região."""
    niche = (niche or "").strip()
    city = (city or "").strip()
    state = (state or "").strip().upper()
    country = (country or "").strip()
    place = " ".join(part for part in (city, state, country) if part)
    base = [
        f"{niche} em {place}",
        f"{niche} {place}",
        f"{niche} {city}" + (f" - {state}" if state else ""),
        f"melhor {niche} {place}",
    ]
    for q in extra or []:
        if q and q not in base:
            base.append(q)
    # remove duplicatas preservando ordem
    seen: set[str] = set()
    out = []
    for q in base:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out


def url_encode(query: str) -> str:
    return quote_plus(query)


class BaseProvider(ABC):
    """Interface dos provedores de descoberta."""

    name = "base"
    label = "Base"
    needs_browser = False
    needs_api_key = False

    def __init__(self, fetcher: Fetcher, api_key: str | None = None, delay: float = 0.8,
                 city: str = "", state: str = "", niche: str = "", country: str = "") -> None:
        self.fetcher = fetcher
        self.api_key = api_key
        self.delay = delay
        self.city = city or ""
        self.state = state or ""
        self.niche = niche or ""
        self.country = country or ""
        self.errors: list[str] = []

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> list[Lead]:
        """Executa uma consulta e devolve leads brutos."""

    def search_many(self, queries: list[str], limit: int = 20) -> list[Lead]:
        import time

        leads: list[Lead] = []
        for q in queries:
            try:
                found = self.search(q, limit=limit)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"{self.name}: {q}: {type(exc).__name__}: {exc}")
                found = []
            for lead in found:
                lead.query = q
                lead.source = self.name
                leads.append(normalize_lead(lead))
            time.sleep(self.delay)
        return leads
