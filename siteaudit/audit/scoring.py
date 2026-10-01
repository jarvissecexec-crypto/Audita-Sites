"""Consolidação dos achados, nota do site e priorização comercial."""

from __future__ import annotations

import math

from ..models import SEVERITY_WEIGHT, Finding

CATEGORIES = ["SEO", "Conteúdo", "Performance", "Design", "Técnico", "Conversão", "Acessibilidade"]

SEVERITY_ORDER = {"critico": 0, "alto": 1, "medio": 2, "baixo": 3, "ok": 4}


def conversion_issues(content: dict, contacts: dict, forms: dict, media: dict, links: dict) -> list[dict]:
    issues: list[dict] = []

    def add(severity, title, detail, fix, impact=""):
        issues.append({"severity": severity, "category": "Conversão", "title": title,
                       "detail": detail, "fix": fix, "impact": impact})

    if not contacts.get("phones") and not contacts.get("whatsapp"):
        add("critico", "Nenhum telefone ou WhatsApp visível",
            "O visitante interessado não tem como falar com a empresa em um toque.",
            "Telefone clicável no header + botão flutuante de WhatsApp.",
            "É a forma mais direta de perder um cliente pronto para comprar.")
    elif not contacts.get("whatsapp"):
        add("alto", "Sem WhatsApp identificado", "Só telefone fixo/móvel; sem link direto para o zap.",
            "Botão do WhatsApp com mensagem pronta: 'Olá, vim pelo site e gostaria de um orçamento'.")

    if not contacts.get("emails"):
        add("baixo", "Nenhum e-mail publicado", "Parte dos clientes prefere e-mail.",
            "E-mail profissional no rodapé e na página de contato.")

    real_forms = [f for f in (forms or {}).get("forms", []) if f.get("field_count", 0) >= 2]
    if not real_forms:
        add("alto", "Sem formulário de contato/orçamento",
            "Quem não liga e não usa WhatsApp não deixa nenhum dado.",
            "Formulário curto (nome, WhatsApp, mensagem) com aviso no WhatsApp do dono.")
    elif len(real_forms) == 1 and not any(f.get("has_email_field") for f in real_forms):
        add("baixo", "Formulário sem campo de e-mail", "Dificulta o follow-up.",
            "Incluir e-mail ou WhatsApp obrigatório.")

    if not (links or {}).get("key_pages", {}).get("contato"):
        add("medio", "Página de contato não encontrada", "Nenhum link claro para /contato.",
            "Página de contato com mapa, telefone, WhatsApp, horários e formulário.")

    if not contacts.get("address"):
        add("alto", "Endereço não identificado", "Negócio local sem endereço perde a busca 'perto de mim'.",
            "Endereço completo + CEP + mapa do Google incorporado.")
    if not contacts.get("maps_embed"):
        add("baixo", "Sem mapa incorporado", "O visitante precisa sair do site para achar a empresa.",
            "Google Maps embed na página de contato.")

    socials = contacts.get("socials") or {}
    if "instagram" not in socials:
        add("medio", "Instagram não vinculado", "Para comércio local, o Instagram é vitrine.",
            "Link do perfil + feed no site.")

    if content.get("word_count", 0) < 180:
        add("alto", f"Pouco conteúdo ({content.get('word_count', 0)} palavras)",
            "Texto raso não responde às dúvidas do cliente nem ranqueia no Google.",
            "Páginas de 400-800 palavras por serviço, com perguntas reais dos clientes.")
    if not (content.get("faq")):
        add("medio", "Nenhuma FAQ", "Dúvidas de preço, prazo e formas de pagamento ficam sem resposta.",
            "Bloco de perguntas frequentes (também vira rich result no Google).")
    if not (content.get("lists")):
        add("baixo", "Serviços não listados de forma escaneável",
            "Sem listas, o visitante precisa ler blocos de texto.",
            "Lista de serviços com ícones e benefícios.")

    if media.get("images_total", 0) < 5:
        add("medio", f"Apenas {media.get('images_total', 0)} imagens",
            "Site sem fotos reais do negócio transmite menos confiança.",
            "Galeria com fotos próprias do espaço, equipe e trabalhos realizados.")
    if not media.get("videos"):
        add("baixo", "Nenhum vídeo incorporado", "Vídeo aumenta o tempo de permanência.",
            "Vídeo curto de apresentação (vertical e horizontal).")

    return issues


def tech_issues(tech: dict, seo: dict) -> list[dict]:
    issues: list[dict] = []

    def add(severity, title, detail, fix, impact=""):
        issues.append({"severity": severity, "category": "Técnico", "title": title,
                       "detail": detail, "fix": fix, "impact": impact})

    flat = tech.get("flat") or []
    if "Google Analytics 4" not in flat and "Google Tag Manager" not in flat:
        add("alto", "Sem analytics instalado",
            "Sem GA4/GTM o dono não sabe de onde vêm os clientes nem qual canal converte.",
            "GA4 + GTM + metas de conversão (clique no WhatsApp, envio de formulário).")
    if "Meta Pixel" not in flat:
        add("medio", "Sem pixel de anúncios", "Não há público para remarketing no Instagram/Facebook.",
            "Meta Pixel + eventos de conversão.")
    if not any(t in flat for t in ("WhatsApp Button", "Tawk.to", "Intercom", "Chatwoot", "JivoChat")):
        add("medio", "Nenhuma ferramenta de atendimento", "Fora o WhatsApp, não há chat,",
            "WhatsApp Business com atalho e horário de atendimento.")

    missing_sec = [k for k, v in (tech.get("security_headers") or {}).items() if not v]
    if len(missing_sec) >= 4:
        add("medio", f"{len(missing_sec)} headers de segurança ausentes",
            ", ".join(missing_sec), "HSTS, CSP, X-Frame-Options, Referrer-Policy.")
    if "Cloudflare" not in flat:
        add("baixo", "Sem CDN identificada", "O site é servido direto da origem, sem cache global.",
            "Cloudflare gratuito (cache, HTTPS, proteção básica).")

    if seo.get("www") and seo.get("https") is False:
        add("baixo", "URL não padronizada", "Com/sem www e HTTP/HTTPS duplicam conteúdo.",
            "Escolher uma canônica e redirecionar 301.")

    return issues


def content_issues(content: dict, seo: dict) -> list[dict]:
    issues: list[dict] = []

    def add(severity, title, detail, fix, impact=""):
        issues.append({"severity": severity, "category": "Conteúdo", "title": title,
                       "detail": detail, "fix": fix, "impact": impact})

    title = (seo.get("title") or "").lower()
    h1 = " ".join(content.get("h1") or []).lower()
    if title and h1 and title[:18] == h1[:18]:
        add("baixo", "Title igual ao H1", "Desperdiça a chance de variar palavras-chave.",
            "Title focado em busca, H1 focado em persuasão.")
    if content.get("word_count", 0) < 60:
        add("critico", f"Site quase sem texto indexável ({content.get('word_count', 0)} palavras)",
            "Página sem conteúdo próprio — comum quando o site é só um iframe de plataforma "
            "externa (cardápio digital, link na bio) ou um 'em construção'.",
            "Site próprio com textos sobre a empresa, serviços, diferenciais e contato — "
            "isso é o que o Google indexa e o que convence o cliente.",
            "Sem texto, o Google não tem o que ranquear e o cliente não entende a proposta.")
    if h1 and len(h1) < 15:
        add("baixo", "H1 curto e genérico", f"H1 atual: '{h1}'.",
            "H1 com benefício principal + cidade (ex.: 'Contabilidade em Novo Hamburgo').")
    headings = content.get("headings") or []
    levels = [h["level"] for h in headings]
    skips = sum(1 for a, b in zip(levels, levels[1:]) if b - a > 1)
    if skips:
        add("baixo", f"{skips} quebras na hierarquia de títulos",
            "Pulos de h2 para h4 atrapalham leitores de tela e SEO.",
            "Hierarquia sequencial de headings.")
    return issues


def accessibility_issues(media: dict, seo: dict, content: dict) -> list[dict]:
    issues: list[dict] = []

    def add(severity, title, detail, fix, impact=""):
        issues.append({"severity": severity, "category": "Acessibilidade", "title": title,
                       "detail": detail, "fix": fix, "impact": impact})

    missing = media.get("images_missing_alt", 0)
    if missing:
        add("medio", f"{missing} imagens sem texto alternativo",
            "Leitores de tela não descrevem a imagem para o usuário.",
            "alt descritivo em todas as imagens de conteúdo.")
    if not seo.get("lang"):
        add("baixo", "Idioma da página não declarado", "Sem lang='pt-BR'.",
            "Declarar o idioma no <html>.")
    if not seo.get("viewport"):
        add("alto", "Não responsivo", "Sem viewport, o site não adapta ao celular.",
            "Layout mobile-first.")
    return issues


def build_findings(
    seo_findings: list[dict],
    design_findings: list[dict],
    perf_findings: list[dict],
    conv_findings: list[dict],
    tech_findings: list[dict],
    cont_findings: list[dict],
    a11y_findings: list[dict],
) -> list[Finding]:
    raw = (seo_findings + design_findings + perf_findings + conv_findings
           + tech_findings + cont_findings + a11y_findings)
    findings = [Finding(**f) for f in raw]
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), CATEGORIES.index(f.category)
                                 if f.category in CATEGORIES else 99))
    return findings


def score_site(findings: list[Finding], perf: dict) -> tuple[int, dict[str, int]]:
    """Nota 0-100 (quanto maior, melhor o site) + nota por categoria.

    Usa decaimento exponencial sobre a soma dos pesos: muitos problemas levam a
    nota lá para baixo, mas nunca a um zero artificial que não distingue sites.
    """
    penalty = sum(SEVERITY_WEIGHT.get(f.severity, 0) for f in findings)
    grade_penalty = {"A": 0, "B": 3, "C": 7, "D": 12, "E": 17}.get(perf.get("perf_grade", "C"), 7)
    raw = 100 * math.exp(-penalty / 300)
    score = int(max(3, min(100, round(raw - grade_penalty))))

    by_cat: dict[str, int] = {}
    for cat in CATEGORIES:
        cat_penalty = sum(SEVERITY_WEIGHT.get(f.severity, 0) for f in findings if f.category == cat)
        by_cat[cat] = int(max(3, min(100, round(100 * math.exp(-cat_penalty / 70)))))
    return score, by_cat


def opportunity_level(score: int | None, has_website: bool) -> tuple[str, str]:
    """Rótulo comercial: quão boa é a oportunidade de vender a reformulação."""
    if not has_website:
        return "Site próprio não localizado", (
            "As fontes consultadas não confirmaram um domínio próprio. Verifique com a empresa "
            "antes de afirmar que ela não possui site."
        )
    if score is None:
        return "Não auditado", "Site não respondeu à auditoria."
    if score >= 85:
        return "Baixa", "Site já bem estruturado (venda consultiva, não reformulação)."
    if score >= 70:
        return "Média", "Melhorias pontuais: CTA, prova social e SEO local."
    if score >= 50:
        return "Alta", "Problemas claros de conversão e SEO — demo lado a lado resolve."
    return "Altíssima", "Site defasado: layout antigo, sem mobile, sem SEO local."


def quick_wins(findings: list[Finding], limit: int = 5) -> list[Finding]:
    """Achados de maior impacto visual para a demo (críticos e altos primeiro)."""
    picked = [f for f in findings if f.severity in ("critico", "alto")][:limit]
    if len(picked) < limit:
        picked += [f for f in findings if f.severity == "medio"][: limit - len(picked)]
    return picked
