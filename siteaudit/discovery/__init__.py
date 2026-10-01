"""Orquestração da descoberta de leads por nicho + região."""

from __future__ import annotations

import os
import re

from ..models import Lead
from ..utils.http import Fetcher
from ..utils.text import strip_accents
from .base import BaseProvider, build_queries, country_code, dedupe, normalize_lead
from .manual import ManualProvider
from .maps import MapsScraperProvider, PlacesApiProvider
from .osm import OsmProvider
from .serp import BingProvider, DuckDuckGoProvider, GoogleWebProvider

PROVIDERS: dict[str, type[BaseProvider]] = {
    "ddg": DuckDuckGoProvider,
    "bing": BingProvider,
    "google": GoogleWebProvider,
    "maps": MapsScraperProvider,
    "places": PlacesApiProvider,
    "osm": OsmProvider,
    "manual": ManualProvider,
}

PROVIDER_HELP = {
    "ddg": "DuckDuckGo HTML — gratuito, sem chave, cobertura média",
    "bing": "Bing Web — gratuito, sem chave, boa cobertura local",
    "google": "Google Web via navegador — precisa de Playwright, pode cair em CAPTCHA",
    "maps": "Google Maps via navegador — melhor qualidade de lead local (telefone/endereço/nota)",
    "places": "Google Places API — rota oficial, requer chave (GOOGLE_MAPS_API_KEY)",
    "osm": "OpenStreetMap (Nominatim/Overpass) — gratuito, sem bloqueio, cobertura parcial",
    "manual": "Sua própria lista (CSV/JSON)",
}


def enrich_websites(
    fetcher: Fetcher,
    leads: list[Lead],
    provider_keys: list[str] | None = None,
    max_lookups: int = 15,
    delay: float = 0.8,
) -> tuple[int, list[str]]:
    """Tenta descobrir o site de leads que só têm nome (busca pelo nome da empresa).

    Útil depois do Maps/OpenStreetMap, que entregam nome e telefone mas nem sempre site.
    """
    import time

    from .base import reg_domain

    errors: list[str] = []
    keys = [k for k in (provider_keys or []) if k in ("bing", "ddg", "google")]
    if not keys:
        return 0, errors

    targets = [l for l in leads if not l.website and l.name][:max_lookups]
    if not targets:
        return 0, errors

    provider = PROVIDERS[keys[0]](fetcher)
    found = 0
    for lead in targets:
        query = f'"{lead.name}" {lead.city or ""} {lead.state or ""} site oficial'.strip()
        try:
            results = provider.search(query, limit=5)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"enriquecimento: {type(exc).__name__}: {exc}")
            results = []
        for candidate in results:
            if not candidate.website:
                continue
            domain = reg_domain(candidate.website)
            # aceita se o domínio tem relação com o nome da empresa
            tokens = [t for t in re.split(r"[^a-z0-9]+", strip_accents(lead.name).lower()) if len(t) > 3]
            domain_clean = strip_accents(domain.split(".")[0]).lower()
            if tokens and any(tok[:6] in domain_clean for tok in tokens):
                lead.website = candidate.website
                lead.has_website = True
                lead.status = "pending"
                lead.source = f"{lead.source}+site"
                found += 1
                break
        time.sleep(delay)
    return found, errors


def discover(
    fetcher: Fetcher,
    niche: str,
    city: str,
    state: str,
    providers: list[str] | None = None,
    limit: int = 20,
    places_key: str | None = None,
    manual_file: str | None = None,
    extra_queries: list[str] | None = None,
    skip_social: bool = True,
    country: str = "",
) -> tuple[list[Lead], list[str]]:
    """Roda todos os provedores pedidos e devolve (leads deduplicados, erros)."""
    providers = providers or ["bing", "ddg"]
    errors: list[str] = []
    all_leads: list[Lead] = []

    queries = build_queries(niche, city, state, extra_queries, country=country) if niche else (extra_queries or [""])
    places_key = places_key or os.getenv("GOOGLE_MAPS_API_KEY")

    for key in providers:
        key = key.strip().lower()
        if key not in PROVIDERS:
            errors.append(f"provedor desconhecido: {key}")
            continue
        if key == "places" and not places_key:
            errors.append("places: ignorado (sem GOOGLE_MAPS_API_KEY / --places-key)")
            continue
        kwargs: dict = {}
        if key == "manual":
            if not manual_file:
                errors.append("manual: ignorado (sem --file)")
                continue
            kwargs["path"] = manual_file
            queries_to_run = [niche or "manual"]
        else:
            queries_to_run = queries
        provider = PROVIDERS[key](fetcher, api_key=places_key,
                                  city=city, state=state, niche=niche, country=country, **kwargs)
        try:
            found = provider.search_many(queries_to_run, limit=limit)
        except Exception as exc:  # noqa: BLE401
            errors.append(f"{key}: {type(exc).__name__}: {exc}")
            found = []
        errors.extend(provider.errors)
        all_leads.extend(found)

    # normalização final
    for lead in all_leads:
        if city and not lead.city:
            lead.city = city
        if state and not lead.state:
            lead.state = state
        if not lead.category:
            lead.category = niche
        normalize_lead(lead)

    leads = dedupe(all_leads)

    if skip_social:
        leads = [l for l in leads if l.website or l.phone or l.maps_url]

    # prioriza quem tem site (para auditar) intercalando com quem não tem (oportunidade)
    leads.sort(key=lambda l: (not l.has_website, -(l.rating or 0)))
    return leads[: max(limit * 2, 40)], errors
