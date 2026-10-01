"""Provedor manual: carrega leads de um CSV ou JSON que você já tenha.

CSV aceito (cabeçalho flexível): nome, site/website/url, telefone, endereço, cidade, uf/estado
JSON aceito: lista de objetos com as mesmas chaves.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re

from ..models import Lead
from .base import BaseProvider, clean_website

NAME_KEYS = ("nome", "name", "empresa", "razao", "titulo", "title")
SITE_KEYS = ("website", "site", "url", "link", "dominio", "domain")
PHONE_KEYS = ("telefone", "phone", "tel", "fone", "whatsapp", "celular")
ADDR_KEYS = ("endereco", "endereço", "address", "logradouro", "rua")
CITY_KEYS = ("cidade", "city", "municipio", "município")
STATE_KEYS = ("uf", "estado", "state", "sigla_uf")
CAT_KEYS = ("categoria", "category", "nicho", "segmento", "tipo")
RATING_KEYS = ("nota", "rating", "estrelas", "avaliacao", "avaliação")
REVIEWS_KEYS = ("avaliacoes", "avaliações", "reviews", "n_avaliacoes", "qtd_avaliacoes")


def _pick(row: dict, keys: tuple[str, ...]) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
    for key in keys:
        if key in lowered and str(lowered[key] or "").strip():
            return str(lowered[key]).strip()
    return ""


class ManualProvider(BaseProvider):
    name = "manual"
    label = "Lista manual (CSV/JSON)"

    def __init__(self, fetcher, api_key: str | None = None, delay: float = 0.0, path: str = "",
                 city: str = "", state: str = "", niche: str = "", country: str = "") -> None:
        super().__init__(fetcher, api_key, delay, city=city, state=state, niche=niche, country=country)
        self.path = path
        self._loaded = False
        self._cache: list[Lead] = []

    def _load(self) -> list[Lead]:
        if self._loaded:
            return self._cache
        self._loaded = True
        path = self.path
        if not path or not os.path.exists(path):
            self.errors.append(f"manual: arquivo não encontrado: {path}")
            return []
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as fh:
                content = fh.read()
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"manual: {exc}")
            return []

        rows: list[dict] = []
        if path.lower().endswith(".json"):
            try:
                data = json.loads(content)
                rows = data if isinstance(data, list) else data.get("leads", [])
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"manual: JSON inválido ({exc})")
        else:
            sample = content[:4096]
            delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
            if sample.count(";") > sample.count(","):
                delimiter = ";"
            rows = list(csv.DictReader(io.StringIO(content), delimiter=delimiter))

        leads: list[Lead] = []
        for row in rows:
            if not isinstance(row, dict) or not row:
                continue
            rating_raw = _pick(row, RATING_KEYS).replace(",", ".")
            reviews_raw = re.sub(r"\D", "", _pick(row, REVIEWS_KEYS))
            lead = Lead(
                rating=float(rating_raw) if rating_raw.replace(".", "", 1).isdigit() else None,
                reviews=int(reviews_raw) if reviews_raw else None,
                name=_pick(row, NAME_KEYS),
                website=clean_website(_pick(row, SITE_KEYS)),
                phone=_pick(row, PHONE_KEYS),
                address=_pick(row, ADDR_KEYS),
                city=_pick(row, CITY_KEYS),
                state=_pick(row, STATE_KEYS),
                category=_pick(row, CAT_KEYS),
            )
            if lead.name or lead.website:
                leads.append(lead)
        self._cache = leads
        return leads

    def search(self, query: str, limit: int = 20) -> list[Lead]:
        leads = self._load()
        if query:
            ql = query.lower()
            for lead in leads:
                lead.category = lead.category or query
                lead.query = query
            # não filtra: a lista manual já é o recorte desejado
            del ql
        return leads[:limit]
