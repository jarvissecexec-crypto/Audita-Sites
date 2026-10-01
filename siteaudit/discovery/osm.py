"""Descoberta via OpenStreetMap (Nominatim + Overpass).

Rota 100% gratuita, sem chave e sem bloqueio por CAPTCHA — útil como plano B
quando o Google Maps barra o IP. A cobertura de dados no Brasil é parcial:
costuma trazer nome, categoria e às vezes telefone/site. Respeite a política de
uso (1 requisição/segundo) — o Fetcher já aplica delay.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from ..models import Lead
from ..utils.text import extract_phones, norm_ws
from .base import BaseProvider, clean_website, country_code

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"

# categorias OSM -> rótulo legível
TAG_MAP = {
    "shop": {"bakery": "Padaria", "hairdresser": "Salão de beleza", "beauty": "Estética",
             "clothes": "Loja de roupas", "furniture": "Móveis", "shoes": "Calçados",
             "convenience": "Mercado", "supermarket": "Supermercado", "car_repair": "Oficina",
             "car": "Automóveis", "florist": "Floricultura", "garden_centre": "Jardinagem",
             "hardware": "Material de construção", "electronics": "Eletrônicos",
             "mobile_phone": "Assistência/ celular", "pet": "Pet shop", "butcher": "Açougue",
             "greengrocer": "Hortifruti", "gift": "Presentes", "jewelry": "Joalheria",
             "sports": "Artigos esportivos", "books": "Livraria", "toys": "Brinquedos",
             "fabric": "Tecidos", "optician": "Ótica", "chemist": "Perfumaria",
             "laundry": "Lavanderia", "musical_instrument": "Instrumentos musicais",
             "stationery": "Papelaria", "bicycle": "Bicicletas", "fishing": "Pesca",
             "trade": "Atacado", "doityourself": "Construção", "interior_decoration": "Decoração"},
    "amenity": {"restaurant": "Restaurante", "cafe": "Café", "fast_food": "Lanchonete",
                "bar": "Bar", "pub": "Bar", "pharmacy": "Farmácia", "bank": "Banco",
                "dentist": "Dentista", "doctors": "Clínica", "clinic": "Clínica",
                "veterinary": "Veterinário", "car_wash": "Lava-rápido",
                "fuel": "Posto", "gym": "Academia", "fitness_centre": "Academia",
                "beauty_salon": "Salão de beleza", "hairdresser": "Cabeleireiro",
                "school": "Escola", "kindergarten": "Escola infantil",
                "driving_school": "Autoescola", "college": "Faculdade",
                "language_school": "Escola de idiomas", "coworking_space": "Coworking",
                "spa": "Spa", "massage": "Massagem", "studio": "Estúdio",
                "theatre": "Teatro", "events_venue": "Espaço de eventos",
                "place_of_worship": "Religioso", "crematorium": "Funerária",
                "funeral_hall": "Funerária", "pet_grooming": "Pet shop",
                "money_lender": "Crédito", "bureau_de_change": "Câmbio",
                "internet_cafe": "Lan house", "photo_studio": "Fotografia"},
    "office": {"accountant": "Contabilidade", "lawyer": "Advocacia", "insurance": "Seguros",
               "company": "Escritório", "telecommunication": "Telecom", "it": "Tecnologia",
               "estate_agent": "Imobiliária", "architect": "Arquitetura",
               "engineer": "Engenharia", "advertising_agency": "Publicidade",
               "marketing": "Marketing", "therapist": "Terapias", "physician": "Consultório",
               "financial": "Financeira", "employment_agency": "Recursos humanos",
               "coworking": "Coworking", "ngo": "ONG", "association": "Associação",
               "graphic_design": "Design gráfico", "web_design": "Web design",
               "logistics": "Logística", "moving_company": "Mudanças", "tax_advisor": "Contabilidade"},
    "craft": {"photographer": "Fotografia", "carpenter": "Marcenaria", "electrician": "Elétrica",
              "plumber": "Hidráulica", "painter": "Pintura", "mechanic": "Mecânica",
              "shoemaker": "Sapateiro", "tailor": "Costura", "jeweller": "Joalheria",
              "bakery": "Panificação", "brewery": "Cervejaria", "confectionery": "Confeitaria",
              "key_cutter": "Chaveiro", "tiler": "Azulejista", "upholsterer": "Estofados",
              "window_construction": "Esquadrias", "metal_construction": "Serralheria",
              "signmaker": "Comunicação visual", "stonemason": "Marmoraria",
              "handicraft": "Artesanato", "dressmaker": "Costura", "glaziery": "Vidraçaria",
              "construction": "Construção", "builder": "Construção",
              "air_conditioning": "Ar-condicionado", "electronics_repair": "Assistência técnica"},
    "leisure": {"fitness_centre": "Academia", "sports_centre": "Centro esportivo",
                "swimming_pool": "Natação", "dance": "Dança", "pitch": "Quadra",
                "bowling_alley": "Boliche", "escape_game": "Escape game",
                "hackerspace": "Makerspace", "trampoline_park": "Parque de trampolins",
                "sauna": "Sauna", "spa": "Spa", "resort": "Resort", "marina": "Marina"},
    "tourism": {"hotel": "Hotel", "hostel": "Hostel", "guest_house": "Pousada",
                "apartment": "Apart-hotel", "travel_agency": "Agência de viagens",
                "chalet": "Chalé", "camp_site": "Camping", "motel": "Motel"},
    "healthcare": {"dentist": "Dentista", "doctor": "Médico", "physiotherapist": "Fisioterapia",
                   "psychotherapist": "Psicoterapia", "nutrition_counselling": "Nutrição",
                   "optometrist": "Ótica", "vaccination_centre": "Vacinação",
                   "laboratory": "Laboratório", "clinic": "Clínica", "hospital": "Hospital"},
    "shop/craft/office": {},
}

# palavras do nicho -> filtros OSM (ajuda a refinar a busca no Overpass)
NICHE_HINTS = [
    (r"pizzaria|pizza", '["cuisine"~"pizza",i]'),
    (r"restaurante", '["amenity"~"restaurant|fast_food",i]'),
    (r"lanch(es|onete)", '["amenity"="fast_food"]'),
    (r"padaria", '["shop"="bakery"]'),
    (r"hamburguer|burger", '["cuisine"~"burger",i]'),
    (r"caf[eé]", '["amenity"="cafe"]'),
    (r"bar\b|pub", '["amenity"~"bar|pub",i]'),
    (r"academia|fitness|muscula", '["leisure"="fitness_centre"]'),
    (r"sal[aã]o|beleza|cabelereir|cabeleireir", '["shop"~"hairdresser|beauty",i]'),
    (r"pr[oó]tese\s*capilar|capilar|peruca|mega ?hair|alongamento|implante\s*capilar|micropigmenta",
     '["shop"~"hairdresser|beauty",i]'),
    (r"barbearia|barbeiro", '["shop"="hairdresser"]'),
    (r"manicure|unha|nail|pod[oó]log", '["shop"="beauty"]'),
    (r"tatuag|piercing", '["shop"~"tattoo|piercing",i]'),
    (r"cl[ií]nica\s+de\s+est[eé]tica|est[eé]tica\s+avançad", '["shop"="beauty"]'),
    (r"dermatolog|psic[oó]log|nutricionista|fonoaudi", '["healthcare"]'),
    (r"hospital|pronto[- ]?socorro|upa\b", '["amenity"~"hospital|clinic",i]'),
    (r"auto ?pe[cç]as|autope[cç]as", '["shop"="car_parts"]'),
    (r"borracharia|pneu", '["shop"="tyres"]'),
    (r"gr[aá]fica|impress[aã]o|xerox", '["shop"="copyshop"]'),
    (r"lavanderia|lavagem", '["shop"="laundry"]'),
    (r"serralheria|vidra[cç]aria|esquadria", '["craft"~"metal_construction|glaziery",i]'),
    (r"advocacia", '["office"="lawyer"]'),
    (r"contabilidad|escrit[oó]rio\s+de\s+contabilidad", '["office"="accountant"]'),
    (r"imobili[aá]ria|corretor", '["office"="estate_agent"]'),
    (r"arquitetura|arquiteto", '["office"="architect"]'),
    (r"engenharia|engenheiro", '["office"="engineer"]'),
    (r"seguros|corretora\s+de\s+seguros", '["office"="insurance"]'),
    (r"psicologia", '["healthcare"="psychotherapist"]'),
    (r"nutri[cç][aã]o", '["healthcare"="nutrition_counselling"]'),
    (r"veterin[aá]rio", '["amenity"="veterinary"]'),
    (r"transportadora|frete|log[ií]stica", '["office"~"logistics|moving_company",i]'),
    (r"cabeleireir", '["shop"="hairdresser"]'),
    (r"spa\b|day\s*spa", '["leisure"="spa"]'),
    (r"est[eé]tica", '["shop"="beauty"]'),
    (r"contab|contador", '["office"~"accountant|tax_advisor",i]'),
    (r"advogad", '["office"="lawyer"]'),
    (r"imobili[aá]ri", '["office"="estate_agent"]'),
    (r"oficina|mec[âa]nic", '["shop"="car_repair"]'),
    (r"farm[aá]cia", '["amenity"="pharmacy"]'),
    (r"cl[ií]nic|m[eé]dic|dentist", '["amenity"~"clinic|dentist|doctors",i]'),
    (r"pet", '["shop"="pet"]'),
    (r"hotel|pousada|hostel", '["tourism"~"hotel|guest_house|hostel",i]'),
    (r"escola", '["amenity"~"school|language_school|driving_school",i]'),
    (r"autoescola", '["amenity"="driving_school"]'),
    (r"loja|roupas|vestu[aá]rio", '["shop"="clothes"]'),
    (r"m[óo]veis|decora", '["shop"~"furniture|interior_decoration",i]'),
    (r"supermercado|mercado|mercadinho", '["shop"~"supermarket|convenience",i]'),
    (r"constru[cç]|material", '["shop"~"hardware|doityourself|trade",i]'),
    (r"lava[- ]?r[aá]pido", '["amenity"="car_wash"]'),
    (r"posto|combust[ií]vel", '["amenity"="fuel"]'),
    (r"floricultura|flores", '["shop"="florist"]'),
    (r"inform[aá]tic|tecnologia|celular|assist", '["shop"~"electronics|computer|mobile_phone",i]'),
    (r"seguro|seguros", '["office"="insurance"]'),
    (r"arquitet", '["office"="architect"]'),
    (r"design|marketing|publicidade|ag[eê]ncia", '["office"~"advertising_agency|marketing|graphic_design|web_design",i]'),
    (r"marcenaria|m[óo]veis planejad", '["craft"~"carpenter|furniture",i]'),
    (r"serralher|vidra", '["craft"~"metal_construction|glaziery",i]'),
    (r"fotograf", '["craft"="photographer"]'),
    (r"pintor|pintura", '["craft"="painter"]'),
    (r"eletricista|el[eé]tric", '["craft"="electrician"]'),
    (r"hidr[aá]ulic|encanador", '["craft"="plumber"]'),
    (r"costura|confec", '["craft"~"tailor|dressmaker",i]'),
    (r"ar-?condicionado|climatiza", '["craft"="air_conditioning"]'),
    (r"mudan[cç]a|frete|transporte", '["office"~"moving_company|logistics",i]'),
    (r"limpeza|faxina", '["shop"="laundry"]'),
    (r"chaveiro", '["craft"="key_cutter"]'),
    (r"estofad", '["craft"="upholsterer"]'),
    (r"marmoraria|pedra", '["craft"="stonemason"]'),
    (r"comunica[cç][aã]o visual|adesiv|placa", '["craft"="signmaker"]'),
    (r"biciclet", '["shop"="bicycle"]'),
    (r"[oó]tica", '["shop"="optician"]'),
    (r"papelaria", '["shop"="stationery"]'),
    (r"livraria", '["shop"="books"]'),
    (r"brinquedo", '["shop"="toys"]'),
    (r"joalheria|joias|joias", '["shop"="jewelry"]'),
    (r"presentes", '["shop"="gift"]'),
    (r"perfumaria|cosm[eé]tic", '["shop"="chemist"]'),
    (r"tecido|aviamento", '["shop"="fabric"]'),
    (r"esporte", '["shop"="sports"]'),
    (r"a[cç]ougue", '["shop"="butcher"]'),
    (r"hortifruti|quitanda", '["shop"="greengrocer"]'),
    (r"jardinagem|jardim", '["shop"="garden_centre"]'),
    (r"instrumento|m[uú]sica", '["shop"="musical_instrument"]'),
    (r"coworking", '["amenity"="coworking_space"]'),
    (r"eventos|festa|buffet", '["amenity"="events_venue"]'),
    (r"massagem|spa|massoterapia", '["leisure"~"spa|massage",i]'),
    (r"dan[cç]a", '["leisure"="dance"]'),
    (r"nata[cç][aã]o|escola de esporte", '["leisure"="swimming_pool"]'),
    (r"ag[eê]ncia de viagens|turismo", '["tourism"="travel_agency"]'),
    (r"veterin[aá]ri", '["amenity"="veterinary"]'),
    (r"fisioterapia", '["healthcare"="physiotherapist"]'),
    (r"psic[oó]log", '["healthcare"="psychotherapist"]'),
    (r"nutricionista|nutri[cç]", '["healthcare"="nutrition_counselling"]'),
    (r"laborat[oó]rio|an[aá]lises", '["healthcare"="laboratory"]'),
]


def _category(tags: dict) -> str:
    for key in ("shop", "amenity", "office", "craft", "leisure", "tourism", "healthcare"):
        value = tags.get(key)
        if value and key in TAG_MAP and value in TAG_MAP[key]:
            return TAG_MAP[key][value]
    for key in ("shop", "amenity", "office", "craft", "leisure", "tourism", "healthcare"):
        if tags.get(key):
            return f"{key}:{tags[key]}".replace("_", " ")
    return ""


def _tags_to_lead(tags: dict, query: str, source: str, lat=None, lon=None) -> Lead:
    name = tags.get("name") or tags.get("operator") or ""
    if not name:
        return Lead()
    website = (tags.get("website") or tags.get("contact:website")
               or tags.get("website:pt") or tags.get("url") or "")
    phone = (tags.get("phone") or tags.get("contact:phone")
             or tags.get("contact:mobile") or tags.get("mobile") or "")
    phones = extract_phones(phone + " " + str(tags))
    street = tags.get("addr:street", "")
    number = tags.get("addr:housenumber", "")
    district = tags.get("addr:suburb") or tags.get("addr:neighbourhood") or ""
    city = tags.get("addr:city", "")
    cep = tags.get("addr:postcode", "")
    parts = [p for p in (street + (", " + number if number else ""), district, city) if p]
    address = " - ".join([p for p in parts if p]) + (f" · CEP {cep}" if cep else "")
    if not address:
        address = tags.get("addr:full", "")
    return Lead(
        name=norm_ws(name),
        website=clean_website(website),
        phone=phones[0] if phones else "",
        address=norm_ws(address)[:200],
        city=city,
        category=_category(tags) or query,
        source=source,
    )


class OsmProvider(BaseProvider):
    """Busca no Nominatim e, se houver cidade, complementa com Overpass."""

    name = "osm"
    label = "OpenStreetMap (Nominatim/Overpass)"

    def search(self, query: str, limit: int = 20) -> list[Lead]:
        leads: list[Lead] = []
        seen: set[str] = set()

        # 1) Nominatim — busca textual (rápida, já traz extratags)
        search_term = self._clean_query(query)
        country = self.country or "Brasil"
        code = country_code(country)
        country_filter = f"&countrycodes={quote(code)}" if code else ""
        language = "pt-BR" if code == "br" else "en"
        url = (f"{NOMINATIM}?q={quote(search_term)}&format=json&addressdetails=1&extratags=1"
               f"&limit={min(limit, 30)}{country_filter}&accept-language={quote(language)}")
        raw = self.fetcher.text(url)
        if raw:
            import json
            try:
                for item in json.loads(raw):
                    tags = dict(item.get("extratags") or {})
                    addr = item.get("address") or {}
                    name = (item.get("display_name") or "").split(",")[0].strip()
                    if name:
                        tags.setdefault("name", name)
                    # Nominatim devolve o tipo fora dos extratags (type=restaurant, etc.)
                    nom_cat, nom_type = item.get("category"), item.get("type")
                    if nom_cat and nom_type and nom_cat not in tags:
                        tags[nom_cat] = nom_type
                    elif nom_type and not any(
                        tags.get(k) for k in ("shop", "amenity", "office", "craft",
                                              "leisure", "tourism", "healthcare")
                    ):
                        for key, mapping in TAG_MAP.items():
                            if nom_type in mapping:
                                tags[key] = nom_type
                                break
                    for key in ("city", "town", "village", "municipality", "suburb"):
                        if addr.get(key):
                            tags.setdefault("addr:city", addr[key])
                            break
                    if addr.get("postcode"):
                        tags.setdefault("addr:postcode", addr["postcode"])
                    lead = _tags_to_lead(tags, query, self.name,
                                         item.get("lat"), item.get("lon"))
                    if lead.name and lead.name.lower() not in seen:
                        seen.add(lead.name.lower())
                        leads.append(lead)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"osm: nominatim: {exc}")

        if len(leads) >= limit:
            return leads[:limit]

        # 2) Overpass — varredura por categoria dentro da caixa da cidade
        bbox = self._bbox(query)
        if bbox:
            for rule in self._overpass_rules(query):
                overpass_query = (
                    f"[out:json][timeout:40];("
                    f'nwr{rule}["name"]{bbox};'
                    f"nwr{rule}[\"name\"][\"website\"]{bbox};);out center tags 60;"
                )
                raw = self.fetcher.text(OVERPASS + "?data=" + quote(overpass_query))
                if not raw:
                    continue
                import json
                try:
                    elements = json.loads(raw).get("elements", [])
                except Exception:
                    continue
                generic = not self._has_hint(query)
                for element in elements:
                    tags = element.get("tags") or {}
                    if generic and not self._matches_niche(tags, query):
                        continue
                    lead = _tags_to_lead(tags, query, self.name)
                    if lead.name and lead.name.lower() not in seen:
                        seen.add(lead.name.lower())
                        leads.append(lead)
                    if len(leads) >= limit:
                        break
                if len(leads) >= limit:
                    break
        if not leads:
            self.errors.append("osm: nada encontrado no OpenStreetMap para esta consulta")
        return leads[:limit]

    @staticmethod
    def _has_hint(query: str) -> bool:
        """Existe dica de nicho para esta consulta?"""
        return any(re.search(pattern, query or "", re.I) for pattern, _ in NICHE_HINTS)

    @staticmethod
    def _matches_niche(tags: dict, query: str) -> bool:
        """Na varredura genérica, só aceita o que tem relação com o nicho."""
        from ..utils.text import strip_accents

        text = strip_accents(" ".join(str(v) for v in tags.values())).lower()
        tokens = [t for t in re.split(r"[^a-z0-9]+", strip_accents(query or "").lower()) if len(t) > 3]
        if not tokens:
            return True
        return any(tok in text for tok in tokens)

    @staticmethod
    def _clean_query(query: str) -> str:
        """Remove palavras que atrapalham a busca textual ('em', 'melhor', ...)."""
        cleaned = re.sub(r"\b(em|no|na|de|do|da|melhor|melhores|os|as|um|uma)\b", " ",
                         query or "", flags=re.I)
        cleaned = re.sub(r"\s*[-/]\s*", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip() or query

    @staticmethod
    def _overpass_rules(query: str) -> list[str]:
        """Traduz o nicho em filtros OSM; sem dica, varre comércios em geral."""
        rules = []
        for pattern, rule in NICHE_HINTS:
            if re.search(pattern, query or "", re.I):
                rules.append(rule)
        if not rules:
            rules = ['["shop"]', '["office"]', '["amenity"]']
        return rules[:2]

    def _bbox(self, query: str) -> str:
        """Caixa aproximada (~13 km) ao redor da cidade, via Nominatim."""
        import json

        place = " ".join(x for x in (self.city, self.state, self.country) if x) or self._clean_query(query)
        code = country_code(self.country or "Brasil")
        country_filter = f"&countrycodes={quote(code)}" if code else ""
        language = "pt-BR" if code == "br" else "en"
        url = (f"{NOMINATIM}?q={quote(place)}&format=json&limit=1&polygon_geojson=0"
               f"{country_filter}&accept-language={quote(language)}")
        raw = self.fetcher.text(url)
        if not raw:
            return ""
        try:
            data = json.loads(raw)
        except Exception:
            return ""
        if not data:
            return ""
        try:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
        except (KeyError, ValueError, IndexError):
            return ""
        delta = 0.06
        return f"({lat - delta:.5f},{lon - delta:.5f},{lat + delta:.5f},{lon + delta:.5f})"
