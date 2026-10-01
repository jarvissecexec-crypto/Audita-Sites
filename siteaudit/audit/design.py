"""Extração de design tokens, estrutura de seções e elementos de conversão.

É o que alimenta a geração automática da demo: paleta, tipografia, raios,
seções existentes, textos de CTA e hierarquia do hero.
"""

from __future__ import annotations

import re
from collections import Counter

from bs4 import BeautifulSoup

from ..utils.text import absolutize, clean_text, host_of, norm_ws, reg_domain, truncate

COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}(?:\s*,\s*[\d.]+)?\s*\)")
FONT_RE = re.compile(r"font-family\s*:\s*([^;}\"']+)", re.I)
SIZE_RE = re.compile(r"font-size\s*:\s*([\d.]+)\s*(px|rem|em|%)", re.I)
RADIUS_RE = re.compile(r"border-radius\s*:\s*([^;}]+)", re.I)

SECTION_PATTERNS = {
    "Hero / destaque": r"hero|banner|slide|destaque|carousel|carrossel|cover",
    "Sobre / quem somos": r"sobre|about|quem-?somos|nossa-historia|historia|a-empresa|institucional",
    "Serviços / produtos": r"servic|soluc|produt|catalog|portfolio|portfólio|cardapio|cardápio|o-que-fazemos",
    "Diferenciais / benefícios": r"diferenc|vantag|benefic|por-?que|why|feature",
    "Galeria / portfólio": r"galeria|gallery|portfolio|portfólio|antes-depois|projetos|fotos",
    "Depoimentos": r"depoiment|testimonial|avaliac|review|clientes|client-?logos",
    "FAQ / dúvidas": r"faq|duvidas|dúvidas|perguntas|accordion",
    "Equipe": r"equipe|team|profissionais|especialistas",
    "Blog / conteúdo": r"blog|noticias|notícias|artigos|news",
    "Contato / formulário": r"contato|contact|fale-?conosco|orcamento|orçament|form|agend",
    "Localização / mapa": r"mapa|localizacao|localização|onde-estamos|maps|endereco",
    "Rodapé": r"footer|rodape|rodapé",
    "Barra de promoção": r"promo|black|desconto|coupon|topbar|top-bar|aviso",
}

CTA_WORDS = (
    "orçamento", "orcamento", "solicitar", "peça", "peca", "peça agora", "agende", "agendar",
    "fale conosco", "falar com", "whatsapp", "entre em contato", "contato", "ligue", "ligar",
    "compre", "comprar", "peça o seu", "saiba mais", "conheça", "conheca", "ver mais",
    "baixar", "assinar", "comece", "experimente", "marcar", "reservar", "visite",
)


def _css_sources(soup: BeautifulSoup, base_url: str, fetcher) -> str:
    css = []
    for tag in soup.find_all("style"):
        css.append(tag.get_text() or "")
    for tag in soup.find_all(attrs={"style": True}):
        css.append(tag.get("style", ""))
    inline_links = [absolutize(t.get("href", ""), base_url) for t in soup.find_all("link", rel=lambda v: v and "stylesheet" in str(v).lower())]
    own = [u for u in inline_links if reg_domain(u) == reg_domain(base_url) or host_of(u) == host_of(base_url)]
    for url in own[:6]:
        if fetcher:
            css.append(fetcher.text(url, respect_robots=True)[:400_000])
    return "\n".join(css)


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    value = value.strip().lower()
    if value.startswith("#"):
        h = value[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) in (6, 8):
            try:
                return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
            except ValueError:
                return None
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", value)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def _cluster(colors: list[tuple[int, int, int]], distance: int = 26) -> list[tuple[int, int, int]]:
    buckets: list[tuple[int, int, int]] = []
    for rgb in colors:
        for idx, rep in enumerate(buckets):
            if sum(abs(a - b) for a, b in zip(rgb, rep)) < distance:
                buckets[idx] = tuple((a + b) // 2 for a, b in zip(rep, rgb))  # type: ignore[assignment]
                break
        else:
            buckets.append(rgb)
    return buckets


def extract_design(soup: BeautifulSoup, base_url: str, fetcher=None, content: dict | None = None) -> dict:
    css = _css_sources(soup, base_url, fetcher)
    html_raw = str(soup)

    raw_colors = [c for c in COLOR_RE.findall(css + " " + html_raw)]
    rgbs = [rgb for rgb in (_hex_to_rgb(c) for c in raw_colors) if rgb]
    # remove branco/preto puros do cálculo de paleta (ruído)
    filtered = [c for c in rgbs if not (c[0] > 245 and c[1] > 245 and c[2] > 245) and not (sum(c) < 30)]
    counter = Counter(filtered)
    top_rgb = _cluster([c for c, _ in counter.most_common(400)])[:10]

    palette = []
    for rgb in top_rgb:
        palette.append({
            "hex": "#%02x%02x%02x" % rgb,
            "rgb": list(rgb),
            "dark": _luminance(rgb) < 0.35,
        })

    # cor de fundo e de texto predominantes para estimar contraste
    bg = "#ffffff"
    fg = "#1a1a1a"
    bg_candidates = re.findall(r"(?:background(?:-color)?|background)\s*:\s*(#[0-9a-fA-F]{3,6}|rgba?\([^)]+\))", css, re.I)
    if bg_candidates:
        parsed = _hex_to_rgb(bg_candidates[0])
        if parsed:
            bg = "#%02x%02x%02x" % parsed
    fg_candidates = re.findall(r"(?:^|[;{\s])color\s*:\s*(#[0-9a-fA-F]{3,6}|rgba?\([^)]+\))", css, re.I)
    if fg_candidates:
        parsed = _hex_to_rgb(fg_candidates[0])
        if parsed:
            fg = "#%02x%02x%02x" % parsed
    contrast = 21.0
    try:
        contrast = _contrast(_hex_to_rgb(bg) or (255, 255, 255), _hex_to_rgb(fg) or (26, 26, 26))
    except Exception:
        pass

    fonts = []
    for value in FONT_RE.findall(css):
        first = value.split(",")[0].strip().strip("\"'")
        if first and first.lower() not in ("inherit", "initial", "unset"):
            if first not in fonts:
                fonts.append(first)
        if len(fonts) >= 6:
            break

    sizes = [float(m.group(1)) for m in SIZE_RE.finditer(css) if m.group(2) == "px"]
    sizes = sorted(set(s for s in sizes if 8 <= s <= 96))
    radii = [norm_ws(r) for r in RADIUS_RE.findall(css)]
    radii = sorted(set(radii), key=lambda r: len(r))[:6]

    # --- seções detectadas (por classe/id dos elementos e textos de heading)
    sections: dict[str, list[str]] = {}
    for element in soup.find_all(True, limit=4000):
        if element.name not in ("section", "div", "header", "footer", "main", "aside", "ul", "nav", "article"):
            continue
        ident = " ".join([str(element.get("id") or ""), " ".join(element.get("class") or [])]).lower()
        if not ident:
            continue
        for label, pattern in SECTION_PATTERNS.items():
            if re.search(pattern, ident) and label not in sections:
                sections[label] = [truncate(clean_text(element.get_text(" ")), 220)]
                break
    # complementa com headings
    for head in (content or {}).get("headings", []):
        text = (head.get("text") or "").lower()
        for label, pattern in SECTION_PATTERNS.items():
            if re.search(pattern, text) and label not in sections:
                sections[label] = [truncate(head["text"], 220)]

    # --- CTAs
    ctas: list[str] = []
    for element in soup.find_all(["a", "button"], limit=800):
        text = clean_text(element.get_text(" "))
        if not text or len(text) > 60:
            continue
        low = text.lower()
        if any(word in low for word in CTA_WORDS):
            if text not in ctas:
                ctas.append(text)
        if len(ctas) >= 8:
            break

    whatsapp_ctas = [c for c in ctas if "whats" in c.lower()]

    hero = {
        "headline": (content or {}).get("h1", [None] or [None])[0] if (content or {}).get("h1") else "",
        "subhead": (content or {}).get("paragraphs", [""])[0] if (content or {}).get("paragraphs") else "",
        "has_slider": bool(soup.select_one('[class*="swiper"], [class*="carousel"], [class*="slide"], [class*="hero"]')),
        "has_video_bg": bool(re.search(r"<video", html_raw, re.I)),
    }

    return {
        "palette": palette,
        "bg_color": bg,
        "text_color": fg,
        "contrast_ratio": contrast,
        "fonts": fonts,
        "font_sizes_px": sizes[:14],
        "border_radius": radii,
        "sections": sections,
        "section_count": len(sections),
        "ctas": ctas,
        "whatsapp_ctas": whatsapp_ctas,
        "hero": hero,
        "has_sticky_menu": bool(re.search(r"position\s*:\s*(sticky|fixed)", css, re.I)),
        "uses_grid_flex": bool(re.search(r"display\s*:\s*(grid|flex)", css, re.I)),
        "css_bytes": len(css),
        "stylesheet_count": len(soup.find_all("link", rel=lambda v: v and "stylesheet" in str(v).lower())),
    }


def design_issues(design: dict, content: dict, contacts: dict) -> list[dict]:  # noqa: C901
    issues: list[dict] = []

    def add(severity: str, title: str, detail: str, fix: str, impact: str = "") -> None:
        issues.append({"severity": severity, "category": "Design", "title": title,
                       "detail": detail, "fix": fix, "impact": impact})

    if design.get("contrast_ratio", 21) < 4.5:
        add("alto", f"Contraste de texto baixo ({design['contrast_ratio']}:1)",
            f"Fundo {design.get('bg_color')} com texto {design.get('text_color')}. O mínimo WCAG AA é 4.5:1.",
            "Ajustar a paleta mantendo a identidade, mas com contraste AA.",
            "Texto difícil de ler no celular aumenta a rejeição.")

    if len(design.get("fonts") or []) > 3:
        add("baixo", f"{len(design['fonts'])} famílias tipográficas diferentes",
            ", ".join(design["fonts"][:5]), "Reduzir para 2 (títulos + texto).")

    if not design.get("uses_grid_flex"):
        add("medio", "Layout sem CSS Grid/Flexbox",
            "Indício de layout antigo (tabelas/posições absolutas) — quebra fácil no celular.",
            "Reconstruir o layout com Grid/Flexbox responsivo.")

    if design.get("section_count", 0) < 5:
        add("alto", f"Apenas {design.get('section_count', 0)} seções identificadas",
            "Faltam blocos que convertem: prova social, diferenciais, FAQ e CTA final.",
            "Estrutura em 8-10 seções: hero, prova social, serviços, diferenciais, galeria, depoimentos, FAQ e contato.")

    expected = ["Depoimentos", "FAQ / dúvidas", "Galeria / portfólio", "Localização / mapa"]
    missing = [s for s in expected if s not in (design.get("sections") or {})]
    if missing:
        add("medio", "Seções de conversão ausentes", "Não encontramos: " + ", ".join(missing),
            "Incluir prova social, FAQ e mapa — aumentam muito a confiança.",
            "Visitante sem prova social e sem respostas às dúvidas não entra em contato.")

    if not content.get("h1"):
        pass  # a ausência de h1 já é reportada como achado de SEO
    elif not design.get("hero", {}).get("headline"):
        add("alto", "Hero com título pouco claro",
            "Existe h1, mas ele não funciona como proposta de valor.",
            "H1 com proposta de valor + cidade e subtítulo de apoio.")

    if not design.get("ctas"):
        add("critico", "Nenhum CTA identificado",
            "Não há botão de ação claro (orçamento, WhatsApp, agendar).",
            "Botão fixo de WhatsApp + CTA primário no hero e repetido ao longo da página.",
            "Sem CTA, o tráfego não vira contato.")
    elif not (contacts.get("whatsapp") or contacts.get("whatsapp_links")):
        add("alto", "Sem botão de WhatsApp visível",
            "No Brasil o WhatsApp é o principal canal de conversão para negócio local.",
            "Botão flutuante de WhatsApp com mensagem pré-preenchida.")

    if not design.get("has_sticky_menu"):
        add("baixo", "Menu não fixo", "Navegação desaparece ao rolar a página.",
            "Header fixo com telefone e WhatsApp sempre visíveis.")

    return issues
