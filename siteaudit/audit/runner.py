"""Orquestrador da auditoria de um site (página inicial + páginas-chave)."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..models import Finding, Lead
from ..utils.http import Fetcher
from ..utils.text import reg_domain, slugify, truncate
from . import design as design_mod
from . import extract as extract_mod
from . import perf as perf_mod
from . import scoring as scoring_mod
from . import seo as seo_mod
from . import tech as tech_mod


def _soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html or "", "lxml")
    except Exception:
        return BeautifulSoup(html or "", "html.parser")


def audit_url(
    fetcher: Fetcher,
    url: str,
    render: bool = False,
    auto_render: bool = True,
    max_pages: int = 4,
    deep_perf: bool = True,
    screenshot_path: str | None = None,
    collect_assets: bool = False,
) -> dict:
    """Roda a auditoria completa de um site e devolve um dicionário serializável."""
    started = time.time()
    result: dict = {
        "url": url,
        "domain": reg_domain(url),
        "audited_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "ok": False,
        "error": "",
    }

    res = fetcher.get(url, render=render, respect_robots=True)
    result["fetch"] = {
        "status_code": res.status_code,
        "final_url": res.final_url or url,
        "elapsed_ms": res.elapsed_ms,
        "html_kb": round(res.size_bytes / 1024, 1),
        "redirects": res.redirects,
        "method": res.method,
        "error": res.error,
    }

    if not res.ok and "robots.txt não permite" not in res.error:
        # tenta https<->http e www antes de desistir
        alt = None
        parsed = urlparse(url)
        if parsed.scheme == "https":
            alt = url.replace("https://", "http://", 1)
        elif parsed.scheme == "http":
            alt = url.replace("http://", "https://", 1)
        if alt:
            res2 = fetcher.get(alt, render=render, respect_robots=True)
            if res2.ok:
                res = res2
                url = alt
                result["url"] = alt
                result["fetch"].update({
                    "status_code": res.status_code, "final_url": res.final_url or alt,
                    "elapsed_ms": res.elapsed_ms, "html_kb": round(res.size_bytes / 1024, 1),
                    "redirects": res.redirects, "method": res.method, "error": "",
                })
    if not res.ok:
        result["error"] = res.error or f"HTTP {res.status_code}"
        result["score"] = None
        result["findings"] = []
        result["elapsed_ms"] = int((time.time() - started) * 1000)
        return result

    if screenshot_path and fetcher.has_playwright():
        try:
            fetcher.render(url, screenshot=screenshot_path, respect_robots=True)
        except Exception:
            pass

    soup = _soup(res.html)
    headers = res.headers

    # "site" que é só um iframe de plataforma externa (Anota AI, Goomer, OlaClick...)
    if auto_render and len(soup.get_text(strip=True)) < 200:
        iframe = soup.find("iframe", src=re.compile(r"^https?://", re.I))
        if iframe and iframe.get("src"):
            target = iframe["src"]
            sub = fetcher.get(target, render=fetcher.has_playwright(), respect_robots=True)
            if sub.ok and len(sub.html or "") > 800:
                res = sub
                soup = _soup(sub.html)
                headers = res.headers
                result["iframe_fallback"] = target
                result["fetch"].update({
                    "status_code": res.status_code, "final_url": res.final_url or target,
                    "elapsed_ms": res.elapsed_ms, "html_kb": round(res.size_bytes / 1024, 1),
                    "method": "iframe: " + target, "error": "",
                })

    # sites em JS entregam um "cascaço" vazio no HTTP: re-busca com navegador real
    if (auto_render and not render and fetcher.has_playwright()
            and (res.size_bytes < 2500 or len(soup.get_text(strip=True)) < 200)):
        rendered = fetcher.render(url, respect_robots=True)
        if rendered.ok and len(rendered.html or "") > len(res.html or ""):
            res = rendered
            soup = _soup(res.html)
            headers = res.headers
            result["fetch"].update({
                "status_code": res.status_code, "final_url": res.final_url or url,
                "elapsed_ms": res.elapsed_ms, "html_kb": round(res.size_bytes / 1024, 1),
                "method": "browser (auto)", "error": "",
            })

    content = extract_mod.extract_content(soup)
    contacts = extract_mod.extract_contacts(soup, res.html, res.final_url or url)
    links = extract_mod.extract_links(soup, res.final_url or url)
    media = extract_mod.extract_media(soup, res.final_url or url)
    forms = extract_mod.extract_forms(soup)
    schema = extract_mod.extract_schema(soup)
    tech = tech_mod.detect_tech(res.html, headers)
    seo = seo_mod.extract_seo(soup, res.final_url or url, headers, fetcher=fetcher)
    design = design_mod.extract_design(soup, res.final_url or url, fetcher=fetcher, content=content)
    perf = perf_mod.extract_perf(
        soup, res.final_url or url, fetcher, res.elapsed_ms, res.size_bytes,
        deep=deep_perf, fetch_method=res.method,
    )

    # --- páginas internas relevantes (enriquecem contatos e inventário)
    pages_crawled: list[dict] = []
    key_pages = links.get("key_pages", {})
    targets = [key_pages[k] for k in ("contato", "sobre", "servicos", "produtos") if k in key_pages]
    for page_url in targets[: max(0, max_pages - 1)]:
        sub = fetcher.get(page_url, render=False, respect_robots=True)
        if not sub.ok:
            continue
        sub_soup = _soup(sub.html)
        sub_content = extract_mod.extract_content(sub_soup)
        sub_contacts = extract_mod.extract_contacts(sub_soup, sub.html, page_url)
        for key in ("phones", "emails", "whatsapp_links"):
            for value in sub_contacts.get(key, []):
                if value not in contacts.get(key, []):
                    contacts[key].append(value)
        for key in ("address", "hours", "maps_embed", "whatsapp", "whatsapp_verified"):
            if not contacts.get(key) and sub_contacts.get(key):
                contacts[key] = sub_contacts[key]
        if not contacts.get("socials"):
            contacts["socials"] = sub_contacts.get("socials") or {}
        pages_crawled.append({
            "url": page_url,
            "role": next((k for k, v in key_pages.items() if v == page_url), ""),
            "title": (sub_soup.title.get_text(strip=True) if sub_soup.title else ""),
            "h1": sub_content.get("h1", [])[:2],
            "word_count": sub_content.get("word_count", 0),
            "status": sub.status_code,
        })
        content["word_count"] += sub_content.get("word_count", 0)
        media["images_total"] += len(sub_soup.find_all("img"))

    # --- achados
    seo_findings = seo_mod.seo_issues(seo, content, media, links, schema)
    design_findings = design_mod.design_issues(design, content, contacts)
    perf_findings = perf_mod.perf_issues(perf)
    conv_findings = scoring_mod.conversion_issues(content, contacts, forms, media, links)
    tech_findings = scoring_mod.tech_issues(tech, seo)
    cont_findings = scoring_mod.content_issues(content, seo)
    a11y_findings = scoring_mod.accessibility_issues(media, seo, content)

    findings = scoring_mod.build_findings(
        seo_findings, design_findings, perf_findings, conv_findings,
        tech_findings, cont_findings, a11y_findings,
    )
    score, by_cat = scoring_mod.score_site(findings, perf)
    level, level_note = scoring_mod.opportunity_level(score, True)

    result.update({
        "ok": True,
        "slug": slugify(contacts.get("phones") and "" or reg_domain(url)),
        "content": content,
        "contacts": contacts,
        "links": links,
        "media": media,
        "forms": forms,
        "schema": schema,
        "tech": tech,
        "seo": seo,
        "design": design,
        "perf": perf,
        "pages": pages_crawled,
        "findings": [f.to_dict() for f in findings],
        "score": score,
        "scores_by_category": by_cat,
        "opportunity": level,
        "opportunity_note": level_note,
        "quick_wins": [f.to_dict() for f in scoring_mod.quick_wins(findings)],
        "counts": {
            "critico": sum(1 for f in findings if f.severity == "critico"),
            "alto": sum(1 for f in findings if f.severity == "alto"),
            "medio": sum(1 for f in findings if f.severity == "medio"),
            "baixo": sum(1 for f in findings if f.severity == "baixo"),
        },
        "elapsed_ms": int((time.time() - started) * 1000),
    })
    return result


def audit_lead(fetcher: Fetcher, lead: Lead, **kwargs) -> Lead:  # noqa: D103
    """Audita o site de um lead e preenche score/achados no próprio objeto."""
    if not lead.website:
        lead.status = "website_not_located"
        lead.score = None
        lead.audit = None
        return lead
    try:
        audit = audit_url(fetcher, lead.website, **kwargs)
    except Exception as exc:  # noqa: BLE001
        lead.status = "error"
        lead.error = f"{type(exc).__name__}: {exc}"
        return lead
    lead.audit = audit
    if audit.get("ok"):
        lead.status = "ok"
        # nome amigável quando só temos a URL
        if not lead.name or lead.name == lead.website:
            lead.name = (audit.get("seo", {}).get("title") or lead.domain or "").split("|")[0][:70]
        lead.score = audit.get("score")
        # enriquece o lead com o que o site informou
        contacts = audit.get("contacts", {})
        if not lead.phone and contacts.get("phones"):
            lead.phone = contacts["phones"][0]
        if not lead.address and contacts.get("address"):
            lead.address = truncate(contacts["address"], 160)
    else:
        lead.status = "error"
        lead.error = audit.get("error", "")
    return lead
