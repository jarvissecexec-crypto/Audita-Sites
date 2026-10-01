"""Briefing em Markdown: o resumo que você usa para (re)construir o site.

Pensado para ser colado em qualquer ferramenta/IA de geração de sites.
"""

from __future__ import annotations

from ..models import Lead
from ..utils.text import truncate


def _bullets(items: list, limit: int = 12) -> str:
    items = [i for i in items if i][:limit]
    return "\n".join(f"- {i}" for i in items) if items else "- (não identificado)"


def build_briefing(lead: Lead, audit: dict | None, demo: dict | None = None) -> str:
    a = audit or {}
    demo = demo or {}
    content = a.get("content", {}) or {}
    contacts = a.get("contacts", {}) or {}
    design = a.get("design", {}) or {}
    tech = a.get("tech", {}) or {}
    seo = a.get("seo", {}) or {}
    perf = a.get("perf", {}) or {}
    media = a.get("media", {}) or {}
    links = a.get("links", {}) or {}

    lines: list[str] = []
    add = lines.append

    add(f"# Briefing — {lead.name or 'Empresa'}")
    add("")
    add(f"- **Site atual:** {lead.website or 'não possui site próprio'}")
    add(f"- **Cidade/UF:** {lead.city or '—'} / {lead.state or '—'}")
    add(f"- **Categoria:** {lead.category or '—'}")
    add(f"- **Nota do site atual:** {lead.score if lead.score is not None else 'n/a'}/100 "
        f"(oportunidade: {a.get('opportunity', '—')})")
    add(f"- **Auditado em:** {a.get('audited_at', '—')}")
    if lead.maps_url:
        add(f"- **Google Maps:** {lead.maps_url}")
    add("")

    add("## 1. Dados de contato (usar no novo site)")
    add("")
    add(f"- Telefone: {contacts.get('phones') or '—'}")
    add(f"- WhatsApp: {contacts.get('whatsapp') or '—'}")
    add(f"- E-mail: {(contacts.get('emails') or ['—'])[0]}")
    add(f"- Endereço: {contacts.get('address') or lead.address or '—'} {contacts.get('cep') or ''}".strip())
    add(f"- Horário: {contacts.get('hours') or '—'}")
    socials = contacts.get("socials") or {}
    add(f"- Redes: {', '.join(f'{k} ({v})' for k, v in socials.items()) or '—'}")
    add("")

    add("## 2. Posicionamento")
    add("")
    add(f"- **Headline sugerida:** {demo.get('headline', '')}")
    add(f"- **Subtítulo:** {demo.get('subhead', '')}")
    add(f"- **Chamada final:** {demo.get('final_headline', '')}")
    add("")
    add("Texto institucional (reescrever mantendo o tom do negócio):")
    add("")
    add(f"> {truncate(demo.get('about', ''), 700)}")
    add("")

    add("## 3. Serviços / produtos (seções a criar)")
    add("")
    for s in demo.get("services", []):
        add(f"- **{s['title']}** — {s['text']}")
    if not demo.get("services"):
        add("- (não identificado — entrevistar o cliente)")
    add("")
    add("Listas brutas encontradas no site original:")
    add("")
    for lst in (content.get("lists") or [])[:5]:
        add(_bullets(lst, 10))
        add("")

    add("## 4. Estrutura sugerida")
    add("")
    add("1. Header fixo com telefone + botão de WhatsApp")
    add("2. Hero: headline com cidade, subtítulo, CTA de orçamento, foto real")
    add("3. Faixa de confiança (nota do Google, prazo, garantia)")
    add("4. Serviços (cards com ícone)")
    add("5. Diferenciais")
    add("6. Galeria de fotos reais")
    add("7. Depoimentos")
    add("8. FAQ")
    add("9. Contato: formulário + mapa + horários + WhatsApp")
    add("10. Rodapé com links, redes e endereço")
    add("")
    add(f"Seções já existentes no site atual: {', '.join((design.get('sections') or {}).keys()) or 'nenhuma clara'}")
    add("")

    add("## 5. Identidade visual")
    add("")
    add(f"- Paleta extraída: {', '.join(c['hex'] for c in (design.get('palette') or [])[:8]) or '—'}")
    add(f"- Cor de destaque escolhida: {demo.get('accent', '—')}")
    add(f"- Fundo/texto: {design.get('bg_color', '—')} / {design.get('text_color', '—')} "
        f"(contraste {design.get('contrast_ratio', '—')}:1)")
    add(f"- Fontes: {', '.join(design.get('fonts') or []) or '—'}")
    add(f"- Raio de borda: {', '.join(design.get('border_radius') or []) or '—'}")
    add(f"- CTAs existentes: {', '.join(design.get('ctas') or []) or '—'}")
    add("")

    add("## 6. O que o novo site precisa resolver")
    add("")
    for f in (a.get("quick_wins") or [])[:10]:
        add(f"- **[{f['severity'].upper()}] {f['title']}** — {f.get('fix', '')}")
    add("")

    add("## 7. Inventário técnico do site atual")
    add("")
    add(f"- Stack: {', '.join(tech.get('flat') or []) or '—'}")
    add(f"- Servidor: {tech.get('server_header') or '—'}")
    add(f"- HTTPS: {'sim' if seo.get('https') else 'não'} · sitemap: {'sim' if seo.get('sitemap_ok') else 'não'} · robots: {'sim' if seo.get('robots_ok') else 'não'}")
    add(f"- Title atual: {seo.get('title') or '—'} ({seo.get('title_len')} caracteres)")
    add(f"- Meta description: {seo.get('description') or '—'}")
    add(f"- Peso estimado: {perf.get('estimated_page_kb')} KB · {perf.get('requests_total_estimate')} requisições · nota {perf.get('perf_grade')}")
    add(f"- Imagens: {media.get('images_total')} ({media.get('images_missing_alt')} sem alt)")
    add(f"- Links internos: {links.get('internal_count')} · externos: {links.get('external_count')}")
    add("")

    add("## 8. Conteúdo extraído (reaproveitar)")
    add("")
    add("### H1")
    add(_bullets(content.get("h1") or [], 5))
    add("")
    add("### H2")
    add(_bullets(content.get("h2") or [], 20))
    add("")
    add("### Palavras-chave do nicho (do site original)")
    add("")
    add(", ".join(f"{kw} ({n})" for kw, n in (content.get("keywords") or [])[:20]) or "—")
    add("")
    if content.get("faq"):
        add("### Perguntas frequentes detectadas")
        add("")
        for item in content["faq"]:
            add(f"- {item['q']}")
        add("")

    add("## 9. Placeholders que precisam de conteúdo real")
    add("")
    for p in demo.get("placeholders", []):
        add(f"- [ ] {p}")
    add("")

    add("## 10. Abordagem sugerida (copy para o primeiro contato)")
    add("")
    add(f"Olá! Tudo bem? Vi que a {lead.name or 'empresa de vocês'} atende em {lead.city or 'sua cidade'} e dei uma "
        f"olhada no site de vocês. Encontrei alguns pontos que estão fazendo vocês perderem clientes que chegam pelo "
        f"celular (principalmente falta de botão de WhatsApp, informações de contato pouco visíveis e SEO local). "
        f"Fiz uma proposta de como o site poderia ficar — posso te mostrar em 2 minutos?")
    add("")
    return "\n".join(lines)
