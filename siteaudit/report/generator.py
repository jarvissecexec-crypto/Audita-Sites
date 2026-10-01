"""Gera todos os artefatos de saída: CSV, JSON, dashboard, relatórios, briefings e demos."""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import __version__
from ..models import Lead
from ..utils.text import slugify, truncate
from . import briefing as briefing_mod
from . import demo as demo_mod

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


# =====================================================================
# Relatório em arquivo único (funciona dentro de iframe/preview isolado)
# =====================================================================

SINGLE_EXTRA_CSS = """
.sa-item{border:1px solid var(--line);border-radius:16px;background:#fff;margin-bottom:14px;overflow:hidden;
         box-shadow:0 6px 20px rgba(15,23,42,.05)}
.sa-head{display:flex;flex-wrap:wrap;gap:12px;align-items:center;padding:16px 18px;cursor:pointer}
.sa-head:hover{background:#fafcff}
.sa-title{font-weight:800;font-size:16px;letter-spacing:-.01em}
.sa-sub{color:var(--muted);font-size:12.5px}
.sa-actions{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap}
.sa-btn{border:1px solid var(--line);background:#fff;border-radius:9px;padding:7px 12px;font-size:13px;
        font-weight:650;cursor:pointer;color:var(--ink)}
.sa-btn.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.sa-panel{display:none;border-top:1px solid var(--line);background:#fff}
.sa-panel.open{display:block}
.sa-demo{position:relative}
.sa-demo .float-whats{position:absolute;bottom:14px;right:14px}
.sa-empty{padding:28px;text-align:center;color:var(--muted)}
.sa-note{background:#f8fafc;border-top:1px solid var(--line);padding:10px 18px;font-size:12.5px;color:var(--muted)}
"""


def _scope_css(css: str, scope: str) -> str:
    """Prefixa todos os seletores com `scope` para não colidir com o CSS do dashboard."""
    out: list[str] = []
    i, n = 0, len(css or "")
    while i < n:
        brace = css.find("{", i)
        if brace == -1:
            out.append(css[i:])
            break
        selector = css[i:brace].strip()
        depth, j = 1, brace + 1
        while j < n and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        body = css[brace:j]
        if selector.startswith("@"):
            if any(selector.startswith(x) for x in ("@media", "@supports", "@container", "@layer")):
                inner_open = body.find("{")
                inner_close = body.rfind("}")
                inner = body[inner_open + 1:inner_close] if inner_open != -1 else ""
                out.append(selector + " {" + _scope_css(inner, scope) + "}")
            else:
                out.append(selector + " " + body)
        else:
            parts = []
            for part in selector.split(","):
                part = part.strip()
                if not part:
                    continue
                if part in ("body", "html", ":root"):
                    parts.append(scope)
                elif part == "*":
                    parts.append(f"{scope} *")
                elif part.startswith(("html.", "html ", "body.")):
                    parts.append(scope + " " + part.split(" ", 1)[-1])
                else:
                    parts.append(f"{scope} {part}")
            out.append(", ".join(parts) + " " + body)
        i = j
    return "".join(out)


def _extract_style(html: str) -> str:
    import re as _re
    blocks = _re.findall(r"<style[^>]*>(.*?)</style>", html or "", _re.S | _re.I)
    return "\n".join(blocks)


def _extract_body(html: str) -> str:
    import re as _re
    m = _re.search(r"<body[^>]*>(.*?)</body>", html or "", _re.S | _re.I)
    return m.group(1) if m else (html or "")


def _unique_ids(html: str, prefix: str) -> str:
    """Evita colisão de âncoras quando vários relatórios vivem no mesmo arquivo."""
    import re as _re

    def repl_id(match):
        return f'id="{prefix}-{match.group(1)}"'

    def repl_href(match):
        return f'href="#{prefix}-{match.group(1)}"'

    html = _re.sub(r'id="?\'?([A-Za-z][\w\-]*)"?', repl_id, html)
    html = _re.sub(r'href="#([A-Za-z][\w\-]*)"', repl_href, html)
    return html


def _score_color(score):  # noqa: D103

    if score is None:
        return "#94a3b8"
    if score >= 80:
        return "#16a34a"
    if score >= 60:
        return "#ca8a04"
    if score >= 40:
        return "#ea580c"
    return "#dc2626"


def _opp_class(level: str) -> str:
    return {"Altíssima": "critico", "Alta": "alto", "Média": "medio",
            "Baixa": "ok", "Não auditado": "neutro",
            "Site próprio não localizado": "neutro"}.get(level, "neutro")


def _unique_slug(lead: Lead, used: set[str]) -> str:
    base = slugify(lead.domain or lead.name or "lead") or "lead"
    slug, i = base, 2
    while slug in used:
        slug = f"{base}-{i}"
        i += 1
    used.add(slug)
    return slug


def build_rows(leads: list[Lead], slugs: dict[int, str], internal_only: bool = False) -> list[dict]:
    rows = []
    for idx, lead in enumerate(leads):
        audit = lead.audit or {}
        slug = slugs.get(idx, slugify(lead.domain or lead.name or "lead"))
        mobile_issue = False
        nowhats = True
        if audit.get("ok"):
            mobile_issue = not audit.get("seo", {}).get("viewport")
            contacts = audit.get("contacts", {})
            nowhats = not bool(contacts.get("whatsapp_verified") and contacts.get("whatsapp"))
        rows.append({
            "name": lead.name or (lead.domain or "Sem nome"),
            "category": truncate(lead.category or "", 34),
            "city": f"{lead.city or ''}{'/' + lead.state if lead.state else ''}".strip(" /") or "—",
            "address": truncate(lead.address or "", 48),
            "site": lead.website,
            "site_short": (lead.domain or "")[:34],
            "has_site": lead.has_website,
            "phone": lead.phone or "",
            "email": ((lead.audit or {}).get("contacts", {}).get("emails") or [""])[0],
            "score": lead.score,
            "score_color": _score_color(lead.score),
            "opportunity": audit.get("opportunity") or ("Site próprio não localizado" if not lead.has_website else "Não auditado"),
            "opp_class": _opp_class(audit.get("opportunity") or ("Site próprio não localizado" if not lead.has_website else "Não auditado")),
            "counts": audit.get("counts") or None,
            "hot": audit.get("opportunity") in ("Alta", "Altíssima"),
            "mobile_issue": mobile_issue,
            "nowhats": nowhats,
            "report": f"relatorios/{slug}.html" if audit.get("ok") else "",
            "demo": f"propostas/{slug}.html" if not internal_only else "",
            "maps_url": lead.maps_url or "",
        })
    return rows


def write_outputs(
    leads: list[Lead],
    out_dir: str | Path,
    niche: str = "",
    city: str = "",
    state: str = "",
    providers: str = "",
    errors: list[str] | None = None,
    show_badge: bool = True,
    internal_only: bool = False,
) -> dict:
    """Escreve todos os arquivos do relatório e devolve metadados do run."""
    out = Path(out_dir)
    (out / "sites").mkdir(parents=True, exist_ok=True)
    (out / "relatorios").mkdir(parents=True, exist_ok=True)
    if not internal_only:
        (out / "propostas").mkdir(parents=True, exist_ok=True)
        (out / "briefings").mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(parents=True, exist_ok=True)

    env = _env()
    tpl_dashboard = env.get_template("dashboard.html.j2")
    tpl_site = env.get_template("site.html.j2")
    tpl_demo = env.get_template("demo.html.j2") if not internal_only else None

    used: set[str] = set()
    slugs: dict[int, str] = {}
    for idx, lead in enumerate(leads):
        slugs[idx] = _unique_slug(lead, used)

    # ------------------------------------------------------------ por site
    demo_cache: dict[int, dict] = {}
    parts: list[dict] = []   # tudo renderizado, para o arquivo único
    for idx, lead in enumerate(leads):
        slug = slugs[idx]
        audit = lead.audit
        demo = demo_mod.build_demo_data(lead, audit, show_badge=show_badge)
        demo_cache[idx] = demo

        # JSON completo da auditoria
        if audit:
            (out / "sites" / f"{slug}.json").write_text(
                json.dumps({"lead": lead.to_dict(), "audit": audit}, ensure_ascii=False, indent=2),
                encoding="utf-8")

        # proposta de demo (serve para quem tem site e para quem não tem)
        demo_html = ""
        if not internal_only and tpl_demo is not None:
            demo_html = tpl_demo.render(d=demo)
            (out / "propostas" / f"{slug}.html").write_text(demo_html, encoding="utf-8")

        # briefing em markdown
        if not internal_only:
            (out / "briefings" / f"{slug}.md").write_text(
                briefing_mod.build_briefing(lead, audit, demo), encoding="utf-8")

        # relatório detalhado (só quem tem site auditado)
        if audit and audit.get("ok"):
            view = dict(audit)
            screenshot_rel = f"../assets/{slug}.png"
            screenshot_abs = out / "assets" / f"{slug}.png"
            view.update({
                "name": lead.name or lead.domain,
                "city": lead.city or "",
                "state": lead.state or "",
                "category": lead.category or "",
                "phone": lead.phone or "",
                "maps_url": lead.maps_url or "",
                "url": audit.get("url") or lead.website,
                "screenshot": screenshot_rel if screenshot_abs.exists() else "",
                "demo_link": (f"../propostas/{slug}.html" if not internal_only else ""),
                "briefing_link": (f"../briefings/{slug}.md" if not internal_only else ""),
            })
            report_html = tpl_site.render(a=view)
            (out / "relatorios" / f"{slug}.html").write_text(report_html, encoding="utf-8")
        else:
            report_html = ""
        parts.append({
            "slug": slug,
            "lead": lead,
            "row": None,
            "demo": demo_html,
            "report": report_html,
            "show_badge": show_badge,
        })

    # ---------------------------------------------------------------- CSV
    csv_path = out / "leads.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow([
            "nome", "categoria", "cidade", "uf", "endereco", "telefone", "whatsapp", "email",
            "site", "tem_site", "nota", "oportunidade", "criticos", "altos", "medios",
            "tem_whatsapp", "responsivo", "sitemap", "https", "nota_google", "avaliacoes",
            "origem", "maps_url", "relatorio", "proposta", "briefing",
        ])
        for idx, lead in enumerate(leads):
            a = lead.audit or {}
            slug = slugs[idx]
            contacts = a.get("contacts", {}) if a else {}
            seo = a.get("seo", {}) if a else {}
            writer.writerow([
                lead.name, lead.category, lead.city, lead.state, lead.address, lead.phone,
                 contacts.get("whatsapp") if contacts.get("whatsapp_verified") else "",
                (contacts.get("emails") or [""])[0] if a else "",
                 lead.website, "sim" if lead.has_website else "não localizado",
                lead.score if lead.score is not None else "",
                a.get("opportunity") or ("Site próprio não localizado" if not lead.has_website else "Não auditado"),
                (a.get("counts") or {}).get("critico", ""), (a.get("counts") or {}).get("alto", ""),
                (a.get("counts") or {}).get("medio", ""),
                 "sim" if contacts.get("whatsapp_verified") and contacts.get("whatsapp") else "não",
                "sim" if seo.get("viewport") else ("não" if a.get("ok") else ""),
                "sim" if seo.get("sitemap_ok") else ("não" if a.get("ok") else ""),
                "sim" if seo.get("https") else ("não" if a.get("ok") else ""),
                lead.rating or "", lead.reviews or "",
                lead.source, lead.maps_url,
                f"relatorios/{slug}.html" if a.get("ok") else "",
                (f"propostas/{slug}.html" if not internal_only else ""),
                (f"briefings/{slug}.md" if not internal_only else ""),
            ])

    # --------------------------------------------------------------- JSON
    scored = [l.score for l in leads if l.score is not None]
    keyword_counter: dict[str, int] = {}
    for lead in leads:
        for kw, n in ((lead.audit or {}).get("content", {}).get("keywords") or [])[:10]:
            keyword_counter[kw] = keyword_counter.get(kw, 0) + n
    top_keywords = sorted(keyword_counter.items(), key=lambda kv: -kv[1])[:20]

    meta = {
        "niche": niche or "—",
        "place": f"{city}{'/' + state if state else ''}".strip(" /") or "—",
        "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "leads_total": len(leads),
        "with_site": sum(1 for l in leads if l.has_website),
        "no_site": sum(1 for l in leads if not l.has_website),
        "avg_score": round(sum(scored) / len(scored)) if scored else "—",
        "hot_leads": sum(1 for l in leads
                         if (l.audit or {}).get("opportunity") in ("Alta", "Altíssima")),
        "providers": providers or "—",
        "errors": errors or [],
        "top_keywords": top_keywords,
        "version": __version__,
    }

    (out / "leads.json").write_text(json.dumps({
        "meta": meta,
        "leads": [l.to_dict() for l in leads],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ----------------------------------------------------------- dashboard
    rows = build_rows(leads, slugs, internal_only=internal_only)
    (out / "index.html").write_text(tpl_dashboard.render(meta=meta, rows=rows), encoding="utf-8")

    single = write_single_file(parts, rows, meta, out)

    # Word (.docx) — opcional, depende do python-docx
    docx_path = ""
    try:
        from .docx_report import write_docx
        place_label = f"{city}{'/' + state if state else ''}".strip(" /")
        docx_path = write_docx(leads, out / "relatorio.docx", meta,
                               title=f"Relatório de oportunidades — {niche} em {place_label}")
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"  ! docx não gerado: {type(exc).__name__}: {exc}")

    return {"meta": meta, "out_dir": str(out), "dashboard": str(out / "index.html"),
            "single_file": single, "docx": docx_path, "csv": str(csv_path),
            "json": str(out / "leads.json")}


def write_single_file(parts: list[dict], rows: list[dict], meta: dict, out: Path) -> str:
    """Gera `relatorio-completo.html`: dashboard + diagnósticos + demos em UM arquivo.

    Serve para abrir em qualquer lugar (e-mail, WhatsApp, preview em iframe isolado,
    pendrive) sem depender de caminhos relativos.
    """
    env = _env()
    tpl_single = env.get_template("single.html.j2")

    demo_css: set[str] = set()
    report_css: set[str] = set()
    items: list[dict] = []

    for part, row in zip(parts, rows):
        slug = part["slug"]
        demo_html = part["demo"] or ""
        report_html = part["report"] or ""

        if demo_html:
            demo_css.add(_scope_css(_extract_style(demo_html), ".sa-demo"))
        if report_html:
            report_css.add(_scope_css(_extract_style(report_html), ".sa-rep"))

        report_body = _unique_ids(_extract_body(report_html), slug) if report_html else ""
        # no arquivo único os links externos viram navegação interna
        report_body = re.sub(
            r'<a href="\.\./propostas/' + re.escape(slug) + r'\.html"[^>]*>',
            '<a href="#" onclick="saToggle(\'' + slug + '-demo\');return false;">',
            report_body)
        report_body = re.sub(
            r'<p><a href="\.\./briefings/' + re.escape(slug) + r'\.md"[^>]*>.*?</p>',
            '<p class="hint">Briefing em Markdown: arquivo <code>briefings/' + slug + '.md</code> '
            '(na pasta do relatório).</p>',
            report_body, flags=re.S)

        items.append({
            "slug": slug,
            "row": row,
            "report_body": report_body,
            "demo_body": _unique_ids(_extract_body(demo_html), "d" + slug.replace("-", "")),
            "has_report": bool(report_html),
            "has_demo": bool(demo_html),
        })

    html = tpl_single.render(
        meta=meta,
        rows=rows,
        items=items,
        demo_css="\n".join(sorted(demo_css)),
        report_css="\n".join(sorted(report_css)),
        extra_css=SINGLE_EXTRA_CSS,
    )
    target = out / "relatorio-completo.html"
    target.write_text(html, encoding="utf-8")
    return str(target)
