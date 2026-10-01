"""Extração de conteúdo, contatos, links, imagens e formulários de uma página.

Tudo aqui é determinístico (parse de HTML) — o que depende de navegador fica em
``fetch.py`` (render) e ``perf.py`` (métricas de carregamento).
"""

from __future__ import annotations

import re
from copy import deepcopy
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..utils.text import (
    CEP_RE,
    absolutize,
    clean_text,
    extract_emails,
    extract_phones,
    extract_socials,
    extract_whatsapp,
    host_of,
    is_probably_page,
    norm_ws,
    reg_domain,
    top_keywords,
    truncate,
    word_count,
)

NAV_HINTS = ("menu", "nav", "header", "footer", "breadcrumb", "cookie", "sidebar")
BOILERPLATE = (
    "todos os direitos reservados", "política de privacidade", "politica de privacidade",
    "termos de uso", "copyright", "desenvolvido por", "cookies",
)


# --------------------------------------------------------------------- texto
def extract_content(soup: BeautifulSoup) -> dict:
    """Texto principal, títulos, listas e FAQ."""
    # Parsing de texto é destrutivo por conveniência; não mutar a árvore que
    # outras etapas usam para ler JSON-LD, CSS, iframes e scripts.
    soup = deepcopy(soup)
    for tag in soup(["script", "style", "noscript", "svg", "template", "iframe"]):
        tag.decompose()

    h1 = [clean_text(t.get_text(" ")) for t in soup.find_all("h1")]
    headings: list[dict] = []
    for level in range(1, 7):
        for tag in soup.find_all(f"h{level}"):
            text = clean_text(tag.get_text(" "))
            if text:
                headings.append({"level": level, "text": truncate(text, 160)})
    h2 = [h["text"] for h in headings if h["level"] == 2]
    h3 = [h["text"] for h in headings if h["level"] == 3]

    # texto principal: prioriza <main>, <article> e depois o corpo
    main = soup.find("main") or soup.find("article") or soup.find("div", {"role": "main"}) or soup.body or soup
    paragraphs = [clean_text(p.get_text(" ")) for p in main.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p) > 25 and not any(b in p.lower() for b in BOILERPLATE)]
    body_text = clean_text(main.get_text(" "))

    # listas (geralmente são serviços/produtos/benefícios)
    lists: list[list[str]] = []
    for ul in main.find_all(["ul", "ol"]):
        items = [clean_text(li.get_text(" ")) for li in ul.find_all("li", recursive=False)]
        items = [i for i in items if 3 < len(i) < 140]
        if len(items) >= 2:
            lists.append(items[:15])
    lists.sort(key=len, reverse=True)

    # perguntas frequentes
    faq: list[dict[str, str]] = []
    for tag in soup.find_all(string=re.compile(r"\?\s*$")):
        parent = tag.parent
        if parent and parent.name in ("h2", "h3", "h4", "strong", "b", "p", "summary", "button"):
            question = clean_text(tag)
            if 12 < len(question) < 200:
                faq.append({"q": question, "a": ""})

    return {
        "h1": [truncate(x, 180) for x in h1 if x],
        "h2": [truncate(x, 160) for x in h2][:40],
        "h3": [truncate(x, 160) for x in h3][:40],
        "headings": headings[:80],
        "paragraphs": paragraphs[:40],
        "main_text": truncate(body_text, 6000),
        "word_count": word_count(body_text),
        "lists": lists[:12],
        "faq": faq[:15],
        "keywords": top_keywords(body_text, 20),
    }


# ----------------------------------------------------------------- contatos
def extract_contacts(soup: BeautifulSoup, html: str, base_url: str = "") -> dict:
    """Telefones, WhatsApp, e-mails, redes sociais, endereço e horários."""
    text = soup.get_text(" ")
    raw = html or ""
    phones = extract_phones(text)
    wa_links = re.findall(r'(?:https?://)?(?:wa\.me|api\.whatsapp\.com/send|web\.whatsapp\.com/send)[^"\'\s<>]*', raw, re.I)
    wa_number = extract_whatsapp(raw)
    if not wa_number:
        for link in wa_links:
            wa_number = extract_whatsapp(link)
            if wa_number:
                break

    emails = extract_emails(text) or extract_emails(raw)
    socials = extract_socials(raw)

    address = ""
    addr_el = soup.select_one('[itemprop="address"], address, .address, .endereco, #endereco')
    if addr_el:
        address = norm_ws(addr_el.get_text(" "))
    if not address:
        street = (r"(?:Rua|R\.|Avenida|Av\.|Travessa|Tv\.|Rodovia|Rod\.|Alameda|Al\.|"
                  r"Praça|Pç\.|Estrada|Est\.|Largo|Beco|Servidão)")
        for pattern in (street + r"\s+[A-ZÀ-Ý][\wÀ-ÿ'\.\- ]{2,60}?,\s*\d{1,6}[^\n]{0,70}",
                        street + r"\s+[A-ZÀ-Ý][\wÀ-ÿ'\.\- ]{2,60}?\s+\d{1,6}[^\n]{0,40}",
                        street + r"\s+[A-ZÀ-Ý][\wÀ-ÿ'\.\- ]{2,60}"):
            m = re.search(pattern, text)
            if m:
                candidate = norm_ws(m.group(0))
                # corta em marcadores que indicam fim do endereço
                candidate = re.split(r"\s+(?:CEP|Telefone|Whats|E-?mail|Fone|Contato)\b",
                                     candidate, flags=re.I)[0].strip(" ,-–—|")
                if len(candidate) >= 8:
                    address = candidate[:200]
                    break

    cep = ""
    m = CEP_RE.search(text)
    if m:
        cep = m.group(0)
        if not address:
            idx = max(0, m.start() - 160)
            address = norm_ws(text[idx:m.end()])

    # horário de funcionamento (só aceita se houver dia da semana ou hora)
    hours = ""
    day = r"(?:segunda|seg\.|terça|terca|ter\.|quarta|qua\.|quinta|qui\.|sexta|sex\.|sábado|sabado|sab\.|domingo|dom\.)"
    clock = r"\d{1,2}\s*(?:h|:\d{2})"
    for pattern in (day + r"[^\n]{0,120}" + day + r"[^\n]{0,60}",
                    r"(?:hor[aá]rio|funcionamento|atendemos|atendimento)[^\n]{0,40}(?:" + day + r"|" + clock + r")[^\n]{0,140}",
                    day + r"[^\n]{0,60}" + clock + r"[^\n]{0,40}"):
        m = re.search(pattern, text, re.I)
        if m:
            candidate = norm_ws(m.group(0))
            if re.search(day, candidate, re.I) or re.search(clock, candidate):
                # corta no fim da primeira frase útil
                hours = re.split(r"(?<=\d)\s+(?=[A-ZÁÉÍÓÚÃÕÇ][a-zãõáéíóúç]{2,}\s)", candidate)[0][:130]
                break

    maps_embed = ""
    iframe = soup.find("iframe", src=re.compile(r"google\.com/maps|maps\.google", re.I))
    if iframe:
        maps_embed = iframe.get("src", "")

    return {
        "phones": phones,
        # Um telefone publicado não prova que o número tenha WhatsApp.
        "whatsapp": wa_number,
        "whatsapp_verified": bool(wa_number),
        "whatsapp_links": [urljoin(base_url, w) if w.startswith("/") else w for w in wa_links[:5]],
        "emails": emails,
        "socials": socials,
        "address": address[:220],
        "cep": cep,
        "hours": hours,
        "maps_embed": maps_embed,
    }


# -------------------------------------------------------------------- links
def extract_links(soup: BeautifulSoup, base_url: str) -> dict:
    """Mapeia links internos/externos, redes sociais e possíveis páginas-chave."""
    host = host_of(base_url)
    domain = reg_domain(base_url)
    internal: list[str] = []
    external: list[str] = []
    nofollow = 0
    empty_anchor = 0

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = clean_text(a.get_text(" "))
        if not text and not a.find("img"):
            empty_anchor += 1
        if a.get("rel") and "nofollow" in [r.lower() for r in a.get("rel")]:
            nofollow += 1
        if href.startswith(("mailto:", "tel:", "whatsapp:", "javascript:")):
            continue
        abs_url = absolutize(href, base_url)
        if not abs_url.startswith("http"):
            continue
        if reg_domain(abs_url) == domain:
            if is_probably_page(abs_url):
                internal.append(abs_url)
        else:
            external.append(abs_url)

    def unique(seq: list[str], cap: int) -> list[str]:
        seen: set[str] = set()
        out = []
        for u in seq:
            k = u.split("#")[0].rstrip("/")
            if k not in seen:
                seen.add(k)
                out.append(u)
            if len(out) >= cap:
                break
        return out

    internal_u = unique(internal, 200)
    external_u = unique(external, 100)

    key_pages: dict[str, str] = {}
    patterns = {
        "contato": r"contat|fale[- ]?conosco|atendimento",
        "sobre": r"sobre|quem[- ]?somos|a-empresa|institucional",
        "servicos": r"servic|soluc",
        "produtos": r"produt|loja|catalogo|catálogo",
        "blog": r"blog|noticias|notícias|artigos",
        "depoimentos": r"depoiment|clientes|avaliac|cases",
        "faq": r"faq|duvidas|dúvidas|perguntas",
        "orcamento": r"orcament|orçament|cotacao|cotação|agend",
    }
    for url in internal_u:
        low = url.lower()
        for key, pat in patterns.items():
            if key not in key_pages and re.search(pat, low):
                key_pages[key] = url

    return {
        "internal_count": len(internal_u),
        "external_count": len(external_u),
        "internal": internal_u[:80],
        "external": external_u[:40],
        "nofollow_count": nofollow,
        "empty_anchor_count": empty_anchor,
        "key_pages": key_pages,
    }


# ------------------------------------------------------------------- imagens
def extract_media(soup: BeautifulSoup, base_url: str) -> dict:
    imgs = soup.find_all("img")
    total = len(imgs)
    missing_alt = 0
    lazy = 0
    modern = 0
    samples: list[dict] = []
    for img in imgs:
        alt = (img.get("alt") or "").strip()
        if not alt:
            missing_alt += 1
        if img.get("loading") == "lazy":
            lazy += 1
        src = img.get("src") or img.get("data-src") or ""
        if re.search(r"\.(webp|avif)$", src, re.I):
            modern += 1
        if len(samples) < 20 and src:
            samples.append({
                "src": absolutize(src, base_url),
                "alt": alt[:120],
                "w": img.get("width"),
                "h": img.get("height"),
            })
    videos = []
    for tag in soup.find_all(["iframe", "video"], src=True):
        s = tag.get("src", "")
        if re.search(r"youtube|vimeo|\.mp4", s, re.I):
            videos.append(absolutize(s, base_url))
    return {
        "images_total": total,
        "images_missing_alt": missing_alt,
        "images_lazy": lazy,
        "images_modern_format": modern,
        "images": samples,
        "videos": videos[:8],
    }


# --------------------------------------------------------------- formulários
def extract_forms(soup: BeautifulSoup) -> dict:
    forms = []
    for form in soup.find_all("form"):
        fields = []
        for inp in form.find_all(["input", "textarea", "select"]):
            ftype = inp.get("type", inp.name)
            if ftype in ("hidden", "submit", "button"):
                continue
            fields.append({
                "name": inp.get("name") or inp.get("id") or "",
                "type": ftype,
                "label": norm_ws((inp.get("aria-label") or inp.get("placeholder") or ""))[:60],
            })
        forms.append({
            "action": form.get("action", ""),
            "method": (form.get("method") or "get").upper(),
            "fields": fields,
            "field_count": len(fields),
            "has_email_field": any("mail" in (f["name"] or "") + (f["type"] or "") for f in fields),
        })
    has_search = bool(soup.find("form", attrs={"role": "search"})) or bool(
        soup.find("input", attrs={"type": "search"})
    )
    return {"forms": forms, "form_count": len(forms), "has_search": has_search}


# ----------------------------------------------------------------- schema.org
def extract_schema(soup: BeautifulSoup) -> dict:
    import json

    types: list[str] = []
    data: list[dict] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type")
            if isinstance(t, list):
                types.extend(t)
            elif t:
                types.append(str(t))
            data.append(item)
    micro = [t.get("itemtype", "").split("/")[-1] for t in soup.find_all(attrs={"itemtype": True})]
    return {
        "types": sorted(set(types))[:20],
        "count": len(data),
        "microdata_types": sorted(set(m for m in micro if m))[:10],
        "has_local_business": any("LocalBusiness" in t or "Organization" in t for t in types),
    }
