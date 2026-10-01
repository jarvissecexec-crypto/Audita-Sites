"""Monta os dados da proposta de novo site (a demo que você mostra ao cliente).

Tudo é derivado do que foi extraído do site original: textos reais, paleta real,
fotos reais, telefone real — com placeholders claros onde faltar conteúdo.
"""

from __future__ import annotations

import html
import re
from urllib.parse import quote_plus

from ..models import Lead
from ..utils.text import norm_ws, truncate

def _pick_accent(palette: list[dict]) -> tuple[str, str]:
    """Escolhe uma cor de destaque usável (nem cinza, nem clara demais)."""
    best = None
    for c in palette:
        r, g, b = c["rgb"]
        mx, mn = max(r, g, b), min(r, g, b)
        saturation = (mx - mn) / mx if mx else 0
        if saturation > 0.25 and 40 < mx < 245:
            score = saturation * 100 + (0 if 60 < (r + g + b) / 3 < 200 else -50)
            if best is None or score > best[0]:
                best = (score, (r, g, b))
    if not best:
        return "#2563eb", "rgba(37,99,235,.14)"
    r, g, b = best[1]
    return f"#{r:02x}{g:02x}{b:02x}", f"rgba({r},{g},{b},.14)"


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name or "") if p and len(p) > 1][:2]
    return "".join(p[0].upper() for p in parts) or "S"


def _phone_digits(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    if d and not d.startswith("55"):
        d = "55" + d
    return d


def _wa_link(phone: str, brand: str) -> str:
    digits = _phone_digits(phone)
    if not digits or len(digits) < 12:
        return "#contato"
    msg = f"Olá! Vim pelo site e gostaria de falar com a equipe da {brand}."
    return f"https://wa.me/{digits}?text={quote_plus(msg)}"


def _services(audit: dict, lead: Lead) -> list[dict]:
    content = audit.get("content", {}) or {}
    lists = content.get("lists") or []
    out: list[dict] = []
    for lst in lists:
        if len(lst) >= 3:
            for item in lst[:6]:
                out.append({"title": truncate(item, 46), "text": truncate(item, 150)})
            break
    if len(out) < 3:
        for h in (content.get("h2") or [])[:6]:
            out.append({"title": truncate(h, 46), "text": truncate(h, 150)})
    if len(out) < 3:
        for index in range(len(out), 3):
            out.append({
                "title": f"Serviço {index + 1} a confirmar",
                "text": "Descrição a validar com a empresa antes da publicação.",
            })
    # remove duplicados
    seen: set[str] = set()
    unique = []
    for item in out:
        if item["title"].lower() in seen:
            continue
        seen.add(item["title"].lower())
        unique.append(item)
    return unique[:6]


def _gallery(audit: dict) -> list[str]:
    imgs = (audit.get("media", {}) or {}).get("images") or []
    urls = []
    for img in imgs:
        src = (img.get("src") or "").strip()
        if not src or not src.startswith("http"):
            continue
        low = src.lower()
        if any(x in low for x in ("logo", "icon", "favicon", "sprite", "placeholder", "pixel", ".svg", "banner_1x1")):
            continue
        try:
            if img.get("w") and int(img["w"]) < 200:
                continue
        except (TypeError, ValueError):
            pass
        if src not in urls:
            urls.append(src)
        if len(urls) >= 8:
            break
    return urls


def _testimonials(audit: dict, lead: Lead) -> list[dict]:
    sections = (audit.get("design", {}) or {}).get("sections") or {}
    out: list[dict] = []
    raw = sections.get("Depoimentos") or []
    for text in raw:
        text = norm_ws(text)
        if 30 < len(text) < 400:
            out.append({"text": truncate(text, 240), "author": "Texto encontrado no site original — confirmar autorização"})
    return out[:3]


def _faq(audit: dict) -> list[dict]:
    content = audit.get("content", {}) or {}
    out: list[dict] = []
    for item in (content.get("faq") or [])[:6]:
        q = norm_ws(item.get("q", ""))
        if q:
            out.append({"q": q, "a": "Resposta a confirmar com a empresa."})
    return out[:6]


def _headline(lead: Lead, audit: dict) -> str:
    content = audit.get("content", {}) or {}
    h1 = (content.get("h1") or [""])[0] if content.get("h1") else ""
    seo_title = (audit.get("seo", {}) or {}).get("title", "")
    base = ""
    if h1 and 10 < len(h1) < 90:
        base = h1
    elif seo_title and 10 < len(seo_title) < 90:
        base = seo_title.split("|")[0].split("–")[0].strip()
    else:
        brand = lead.name or "Sua empresa"
        niche = (lead.category or "serviços").lower()
        base = f"{brand}: {niche} em {lead.city or 'sua região'}"
    safe = html.escape(base)
    if lead.city:
        city_esc = html.escape(lead.city)
        safe = re.sub(re.escape(city_esc), f"<span>{city_esc}</span>", safe, count=1, flags=re.I)
    return safe


def build_demo_data(lead: Lead, audit: dict | None, show_badge: bool = True) -> dict:
    """Consolida tudo que o template da proposta precisa."""
    audit = audit or {}
    content = audit.get("content", {}) or {}
    contacts = audit.get("contacts", {}) or {}
    design = audit.get("design", {}) or {}

    brand = lead.name or (content.get("h1") or [""])[0] or "Sua empresa"
    brand = truncate(brand, 46)
    accent, accent_soft = _pick_accent(design.get("palette") or [])

    phone = lead.phone or (contacts.get("phones") or [""])[0]
    # Older saved audits used to copy any phone number into this field. Only
    # trust records produced by the explicit WhatsApp-link detector.
    whats = contacts.get("whatsapp") if contacts.get("whatsapp_verified") else ""
    paragraphs = content.get("paragraphs") or []
    about = " ".join(paragraphs[:3]) if paragraphs else ""
    if len(about) < 120:
        about = "Apresentação institucional a confirmar com a empresa antes da publicação."
    about = truncate(about, 620)

    gallery = _gallery(audit)
    hero_image = gallery[0] if gallery else ""
    about_image = gallery[1] if len(gallery) > 1 else ""

    city = lead.city or "sua região"
    niche = (lead.category or "").lower() or "serviços"

    return {
        "brand": brand,
        "initials": _initials(brand),
        "city": city,
        "niche": niche,
        "title": f"{brand} — proposta de novo site",
        "accent": accent,
        "accent_soft": accent_soft,
        "show_badge": show_badge,
        "headline": _headline(lead, audit),
        "subhead": truncate(
            paragraphs[0] if paragraphs else
            f"Apresentação dos serviços de {niche} em {city} — texto a confirmar com a empresa.", 260),
        "phone": phone,
        "phone_digits": _phone_digits(phone),
        "whatsapp": whats,
        "whatsapp_link": _wa_link(whats, brand),
        "email": (contacts.get("emails") or [""])[0],
        "address": truncate(contacts.get("address") or (lead.address or ""), 160),
        "hours": contacts.get("hours") or "",
        "maps_url": lead.maps_url or f"https://www.google.com/maps/search/?api=1&query={quote_plus(brand + ' ' + city)}",
        "rating": round(lead.rating, 1) if lead.rating else None,
        "reviews": lead.reviews or 0,
        "trust": [],
        "services": _services(audit, lead),
        "about": about,
        "differentials": [],
        "gallery": gallery,
        "hero_image": hero_image,
        "about_image": about_image,
        "testimonials": _testimonials(audit, lead),
        "faq": _faq(audit),
        "final_headline": f"Vamos conversar sobre o seu {niche}?",
        "final_text": f"Fale agora com a equipe da {brand} em {city} e receba uma proposta rápida e sem compromisso.",
        "year": 2026,
        "placeholders": [
            "Confirmar serviços, descrições, horários e demais informações com a empresa.",
            "Confirmar autorização antes de reutilizar fotos ou depoimentos do site original.",
        ],
    }
