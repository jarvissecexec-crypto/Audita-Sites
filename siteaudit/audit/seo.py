"""Extração e diagnóstico de SEO on-page."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..utils.text import norm_ws, truncate

IDEAL_TITLE = (30, 60)
IDEAL_DESC = (70, 160)


def _meta(soup: BeautifulSoup, **attrs) -> str:
    tag = soup.find("meta", attrs=attrs)
    return norm_ws(tag.get("content", "")) if tag else ""


def extract_seo(soup: BeautifulSoup, final_url: str, headers: dict, fetcher=None) -> dict:
    title = norm_ws(soup.title.get_text(" ")) if soup.title else ""
    description = _meta(soup, name="description") or _meta(soup, property="og:description")
    keywords = _meta(soup, name="keywords")
    canonical = ""
    link_canonical = soup.find("link", rel=lambda v: v and "canonical" in str(v).lower())
    if link_canonical:
        canonical = link_canonical.get("href", "")

    robots_meta = _meta(soup, name="robots")
    viewport = _meta(soup, name="viewport")
    charset = ""
    meta_charset = soup.find("meta", attrs={"charset": True})
    if meta_charset:
        charset = meta_charset.get("charset", "")
    else:
        ctype = (headers or {}).get("content-type", "")
        m = re.search(r"charset=([\w\-]+)", ctype, re.I)
        charset = m.group(1) if m else ""

    html_tag = soup.find("html")
    lang = html_tag.get("lang", "") if html_tag else ""

    og = {}
    for tag in soup.find_all("meta", attrs={"property": re.compile(r"^og:")}):
        og[tag.get("property", "")] = norm_ws(tag.get("content", ""))[:200]
    twitter = {}
    for tag in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:")}):
        twitter[tag.get("name", "")] = norm_ws(tag.get("content", ""))[:200]

    favicon = ""
    for rel in ("icon", "shortcut icon", "apple-touch-icon"):
        tag = soup.find("link", rel=lambda v, r=rel: v and r in str(v).lower())
        if tag and tag.get("href"):
            favicon = tag["href"]
            break

    hreflang = [t.get("hreflang") for t in soup.find_all("link", attrs={"hreflang": True})]

    parsed = urlparse(final_url)
    https = parsed.scheme == "https"
    www = parsed.netloc.lower().startswith("www.")

    # sitemap / robots
    sitemap_ok = sitemap_url = robots_ok = False
    robots_url = ""
    if fetcher:
        base = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = base + "/robots.txt"
        robots_txt = fetcher.text(robots_url)
        robots_ok = bool(robots_txt) and "user-agent" in robots_txt.lower()
        for candidate in [u for u in fetcher.sitemaps(final_url)] or [base + "/sitemap.xml", base + "/sitemap_index.xml"]:
            if not candidate:
                continue
            body = fetcher.text(candidate, respect_robots=True)
            if body and "<urlset" in body.lower() or "<sitemapindex" in (body or "").lower():
                sitemap_ok, sitemap_url = True, candidate
                break

    return {
        "title": truncate(title, 200),
        "title_len": len(title),
        "description": truncate(description, 400),
        "description_len": len(description),
        "keywords": keywords[:200],
        "canonical": canonical,
        "robots_meta": robots_meta,
        "viewport": viewport,
        "charset": charset,
        "lang": lang,
        "og": og,
        "twitter": twitter,
        "favicon": favicon,
        "hreflang": hreflang,
        "https": https,
        "www": www,
        "robots_ok": robots_ok,
        "sitemap_ok": sitemap_ok,
        "sitemap_url": sitemap_url,
        "url_slug": parsed.path.rstrip("/") or "/",
    }


def seo_issues(seo: dict, content: dict, media: dict, links: dict, schema: dict) -> list[dict]:
    """Problemas de SEO já no formato {severity, title, detail, fix}."""
    issues: list[dict] = []

    def add(severity: str, title: str, detail: str, fix: str, impact: str = "") -> None:
        issues.append({"severity": severity, "category": "SEO", "title": title,
                       "detail": detail, "fix": fix, "impact": impact})

    if not seo.get("title"):
        add("critico", "Página sem <title>", "O título é o principal sinal de SEO e o texto que aparece no Google.",
            "Título único com nicho + cidade (ex.: 'Pizzaria em Igrejinha - RS | Nome').",
            "Sem título, a página não disputa as primeiras posições.")
    elif not (IDEAL_TITLE[0] <= seo["title_len"] <= IDEAL_TITLE[1]):
        add("medio", f"Title com {seo['title_len']} caracteres",
            f"Fora da faixa ideal ({IDEAL_TITLE[0]}-{IDEAL_TITLE[1]}): '{seo['title'][:90]}'",
            "Reescrever o title com 30-60 caracteres, incluindo nicho e cidade.")

    if not seo.get("description"):
        add("alto", "Sem meta description", "O Google gera o snippet sozinho, sem controle sobre a mensagem de venda.",
            "Meta description de 70-160 caracteres com chamada para ação.")
    elif not (IDEAL_DESC[0] <= seo["description_len"] <= IDEAL_DESC[1]):
        add("baixo", f"Meta description com {seo['description_len']} caracteres",
            "Fora da faixa ideal (70-160).", "Ajustar para caber inteira no resultado de busca.")

    h1s = content.get("h1") or []
    if not h1s:
        add("alto", "Nenhum <h1> na página", "O h1 diz ao Google (e ao visitante) do que se trata a página.",
            "Um h1 por página com a proposta de valor + cidade.")
    elif len(h1s) > 1:
        add("baixo", f"{len(h1s)} elementos <h1>", "Mais de um h1 dilui a hierarquia semântica.",
            "Manter um único h1 e rebaixar os demais para h2.")

    if not seo.get("canonical"):
        add("medio", "Sem tag canonical", "Risco de conteúdo duplicado (com/sem www, parâmetros de URL).",
            "Canonical apontando para a versão preferida da URL.")

    if not seo.get("lang"):
        add("medio", "Atributo lang ausente", "Sem lang='pt-BR' o Google e leitores de tela erram o idioma.",
            "Adicionar <html lang='pt-BR'>.")

    if not seo.get("viewport"):
        add("critico", "Sem meta viewport", "O site não se adapta ao celular — hoje a maioria dos acessos é mobile.",
            "Layout responsivo + <meta name='viewport' content='width=device-width, initial-scale=1'>.")
    elif "width=device-width" not in seo["viewport"]:
        add("alto", "Viewport incorreto", f"Valor atual: '{seo['viewport']}'",
            "Usar width=device-width, initial-scale=1.")

    if not seo.get("https"):
        add("critico", "Site sem HTTPS", "Chrome marca como 'não seguro' e o Google rebaixa o site.",
            "Certificado SSL gratuito (Let's Encrypt) + redirecionamento 301.")

    if not seo.get("og", {}).get("og:title") or not seo.get("og", {}).get("og:image"):
        add("medio", "Open Graph incompleto", "Links compartilhados no WhatsApp/Instagram ficam sem imagem e sem título.",
            "og:title, og:description, og:image (1200x630) e twitter:card.")

    if not seo.get("favicon"):
        add("baixo", "Sem favicon", "Marca ausente na aba do navegador e nos favoritos.", "Favicon 32x32 + apple-touch-icon.")

    if not seo.get("robots_ok"):
        add("medio", "robots.txt ausente ou inválido", "Sem robots.txt o Google não recebe dicas de indexação.",
            "robots.txt apontando para o sitemap.xml.")
    if not seo.get("sitemap_ok"):
        add("alto", "sitemap.xml não encontrado", "Dificulta a descoberta e a indexação das páginas.",
            "Gerar sitemap.xml e enviar no Google Search Console.")

    if not schema.get("has_local_business"):
        add("alto", "Sem dados estruturados (Schema.org)",
            "Sem LocalBusiness/Organization a empresa não aparece com estrelas, telefone e endereço no Google.",
            "JSON-LD LocalBusiness com nome, telefone, endereço, horários e avaliações.")
    if not schema.get("types"):
        add("medio", "Nenhum JSON-LD na página", "Sem marcação semântica para o Google entender a página.",
            "Adicionar JSON-LD (Organization + LocalBusiness + Service).")

    missing_alt = media.get("images_missing_alt", 0)
    total_img = media.get("images_total", 0)
    if total_img and missing_alt / max(total_img, 1) > 0.3:
        add("medio", f"{missing_alt} de {total_img} imagens sem alt",
            "Perde tráfego do Google Imagens e prejudica acessibilidade.",
            "alt descritivo em todas as imagens (com nicho e cidade quando fizer sentido).")

    if links.get("empty_anchor_count", 0) > 3:
        add("baixo", f"{links['empty_anchor_count']} links sem texto", "Links 'clique aqui' não passam contexto.",
            "Usar âncoras descritivas.")

    return issues
