"""Geração de relatórios em Word (.docx).

Dois documentos:
  * ``write_docx``       — relatório da varredura (resumo, mapa de leads, diagnóstico por empresa)
  * ``write_guide_docx`` — guia de uso da ferramenta (o que é, o que precisa, comandos)

O docx é o formato mais fácil de entregar: abre no Word, Google Docs e LibreOffice
sem depender de pasta, navegador ou servidor.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from ..models import Lead

ACCENT = RGBColor(0x1E, 0x3A, 0x8A)
MUTED = RGBColor(0x5B, 0x64, 0x78)
SEV_LABEL = {"critico": "CRÍTICO", "alto": "ALTO", "medio": "MÉDIO", "baixo": "BAIXO", "ok": "OK"}

# ----------------------------------------------------------------- helpers


def _shade(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _setup(doc: Document) -> None:
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    style.paragraph_format.space_after = Pt(6)
    for section in doc.sections:
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)


def _table(doc: Document, headers: list[str], rows: list[list[str]], widths: list[float] | None = None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    header_cells = table.rows[0].cells
    for i, text in enumerate(headers):
        header_cells[i].text = ""
        run = header_cells[i].paragraphs[0].add_run(str(text))
        run.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        _shade(header_cells[i], "1E3A8A")
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run("" if value is None else str(value))
            run.font.size = Pt(9)
    if widths:
        for row in table.rows:
            for i, width in enumerate(widths):
                row.cells[i].width = Inches(width)
    return table


def _kv(doc: Document, label: str, value: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(f"{label}: ")
    run.bold = True
    p.add_run(value)


# ------------------------------------------------------------- relatório


def write_docx(leads: list[Lead], path: str | Path, meta: dict | None = None, title: str = "") -> str:
    """Escreve o relatório da varredura em .docx."""
    meta = meta or {}
    doc = Document()
    _setup(doc)

    # ---- capa
    h = doc.add_heading(title or f"Relatório de oportunidades — {meta.get('niche', '')}", level=0)
    for run in h.runs:
        run.font.color.rgb = ACCENT
    sub = doc.add_paragraph()
    sub_run = sub.add_run(
        f"{meta.get('place', '')} · gerado em {meta.get('generated_at', '')} · "
        f"fontes: {meta.get('providers', '')}"
    )
    sub_run.italic = True
    sub_run.font.color.rgb = MUTED
    sub_run.font.size = Pt(10)

    # ---- 1. resumo
    doc.add_heading("1. Resumo executivo", level=1)
    doc.add_paragraph(
        "Levantamento de empresas do nicho na região, com auditoria automática do site de cada uma. "
            "A nota vai de 0 a 100 e resume achados técnicos observados durante a coleta. "
            "Ela não mede conversão nem garante potencial comercial; valide os achados antes da abordagem."
    )
    _table(
        doc,
        ["Indicador", "Valor"],
        [
            ["Empresas encontradas", meta.get("leads_total", len(leads))],
            ["Com site próprio", meta.get("with_site", sum(1 for l in leads if l.website))],
            ["Site próprio não localizado", meta.get("no_site", sum(1 for l in leads if not l.website))],
            ["Nota média dos sites", meta.get("avg_score", "—")],
            ["Oportunidades altas", meta.get("hot_leads", "—")],
        ],
        widths=[3.0, 1.4],
    )

    # ---- 2. mapa de leads
    doc.add_heading("2. Mapa de oportunidades", level=1)
    rows = []
    for lead in sorted(leads, key=lambda l: (l.score is None, l.score or 0)):
        audit = lead.audit or {}
        rows.append([
            (lead.name or "—")[:38],
            lead.city or "—",
            lead.phone or "—",
            (lead.domain or "não localizado")[:30],
            lead.score if lead.score is not None else "—",
            audit.get("opportunity") or ("Site próprio não localizado" if not lead.website else "Não auditado"),
        ])
    _table(doc, ["Empresa", "Cidade", "Telefone", "Site", "Nota", "Oportunidade"],
           rows, widths=[2.0, 1.0, 1.15, 1.6, 0.45, 1.05])

    # ---- 3. empresas sem domínio próprio localizado
    no_site = [l for l in leads if not l.website]
    doc.add_heading("3. Empresas sem domínio próprio localizado", level=1)
    if no_site:
        doc.add_paragraph(
            "As fontes consultadas não localizaram um domínio próprio para estas empresas. "
            "Isso não prova que elas não tenham site; confirme a informação antes de abordar "
            "ou propor presença digital do zero."
        )
        _table(
            doc,
            ["Empresa", "Telefone", "Categoria", "Nota Google", "Avaliações"],
            [[(l.name or "—")[:38], l.phone or "—", (l.category or "—")[:26],
              l.rating or "—", l.reviews or "—"] for l in no_site],
            widths=[2.3, 1.3, 1.7, 0.85, 0.85],
        )
    else:
        doc.add_paragraph("As fontes consultadas localizaram um domínio próprio para todas as empresas desta varredura.")

    # ---- 4. diagnóstico por empresa
    audited = [l for l in leads if (l.audit or {}).get("ok")]
    if audited:
        doc.add_page_break()
        doc.add_heading("4. Diagnóstico por empresa", level=1)
        for lead in sorted(audited, key=lambda l: (l.score if l.score is not None else 999)):
            audit = lead.audit or {}
            doc.add_heading(f"{lead.name} — nota {lead.score}/100 ({audit.get('opportunity', '')})", level=2)

            contacts = audit.get("contacts", {})
            perf = audit.get("perf", {})
            tech = audit.get("tech", {})
            content = audit.get("content", {})
            seo = audit.get("seo", {})
            _table(
                doc,
                ["Campo", "Valor"],
                [
                    ["Site", audit.get("url", lead.website)],
                    ["Telefone", ", ".join(contacts.get("phones") or []) or "—"],
                    ["WhatsApp", contacts.get("whatsapp") if contacts.get("whatsapp_verified") else "não identificado"],
                    ["E-mail", ", ".join(contacts.get("emails") or []) or "—"],
                    ["Endereço", contacts.get("address") or "—"],
                    ["Horário", contacts.get("hours") or "—"],
                    ["Redes", ", ".join((contacts.get("socials") or {}).keys()) or "—"],
                    ["Nota Google / avaliações", f"{lead.rating or '—'} · {lead.reviews or '—'}"],
                    ["Tecnologia", ", ".join(tech.get("flat", [])[:10]) or "—"],
                    ["Desempenho", f"nota {perf.get('perf_grade', '—')} · "
                                   f"{perf.get('estimated_page_kb', '—')} KB · "
                                   f"{perf.get('requests_total_estimate', '—')} requisições · "
                                   f"duração da resposta {perf.get('response_duration_ms', '—')} ms"],
                    ["Conteúdo", f"{content.get('word_count', 0)} palavras · "
                                 f"{len(content.get('h1') or [])} h1 · "
                                 f"{len(content.get('headings') or [])} títulos"],
                    ["Title atual", (seo.get("title") or "—")[:90]],
                    ["Páginas visitadas", ", ".join(p.get("role") or p.get("url", "") for p in (audit.get("pages") or [])) or "—"],
                ],
                widths=[1.5, 5.0],
            )

            scores = audit.get("scores_by_category") or {}
            if scores:
                _kv(doc, "Notas por categoria",
                    " · ".join(f"{k}: {v}" for k, v in scores.items()))

            doc.add_paragraph()
            p = doc.add_paragraph()
            p.add_run("Principais achados e o que entregar").bold = True
            for finding in (audit.get("findings") or [])[:8]:
                sev = SEV_LABEL.get(finding.get("severity", ""), finding.get("severity", ""))
                line = doc.add_paragraph(style="List Bullet")
                run = line.add_run(f"[{sev}] {finding.get('title', '')}")
                run.bold = finding.get("severity") in ("critico", "alto")
                if finding.get("detail"):
                    line.add_run(f" — {finding['detail']}")
                if finding.get("fix"):
                    fix = doc.add_paragraph(style="List Bullet 2")
                    fix_run = fix.add_run(f"Solução: {finding['fix']}")
                    fix_run.italic = True
            doc.add_paragraph()

    # ---- 5. padrões do nicho
    doc.add_heading("5. Padrões do nicho", level=1)
    if audited:
        total = len(audited)
        def pct(n: int) -> str:
            return f"{n} de {total} ({round(100 * n / total)}%)"

        no_whats = sum(1 for l in audited if not l.audit["contacts"].get("whatsapp_verified"))
        slow = sum(1 for l in audited if l.audit["perf"].get("measurement_method", "http") == "http"
                   and l.audit["perf"].get("response_duration_ms", 0) > 800)
        thin = sum(1 for l in audited if l.audit["content"].get("word_count", 0) < 300)
        no_schema = sum(1 for l in audited if not l.audit["schema"].get("has_local_business"))
        no_sitemap = sum(1 for l in audited if not l.audit["seo"].get("sitemap_ok"))
        no_https = sum(1 for l in audited if not l.audit["seo"].get("https"))
        poor_mobile = sum(1 for l in audited if not l.audit["seo"].get("viewport"))
        no_ga = sum(1 for l in audited if not any(
            t in l.audit["tech"].get("flat", []) for t in ("Google Analytics 4", "Google Tag Manager")))
        for text in (
            f"Sem WhatsApp ou telefone visível: {pct(no_whats)}",
            f"Site sem dados de empresa para o Google (Schema.org LocalBusiness): {pct(no_schema)}",
            f"Resposta HTTP acima de 0,8 s: {pct(slow)}",
            f"Pouco texto para ranquear (menos de 300 palavras): {pct(thin)}",
            f"Sem sitemap.xml: {pct(no_sitemap)}",
            f"Sem HTTPS: {pct(no_https)}",
            f"Sem versão de celular (viewport): {pct(poor_mobile)}",
            f"Sem analytics instalado: {pct(no_ga)}",
        ):
            doc.add_paragraph(text, style="List Bullet")
        doc.add_paragraph(
            "Esses números são o seu argumento de venda: o problema não é de uma empresa, "
            "é do nicho inteiro — e você já tem a solução montada."
        )
    else:
        doc.add_paragraph("Nenhum site auditado nesta varredura.")

    # ---- 6. roteiro de abordagem
    doc.add_heading("6. Roteiro de abordagem", level=1)
    for text in (
        "Comece revisando as empresas para as quais nenhum domínio próprio foi localizado. "
        "Confirme isso com o negócio antes de propor um site do zero.",
        "Para quem tem site: abra o diagnóstico, mostre 2 ou 3 achados críticos e só então abra a proposta "
        "de site novo. O contraste 'antes e depois' é o que vende.",
        "Leve o número da nota. 'Seu site está 43/100' é concreto, gera curiosidade e abre conversa.",
        "Feche a reunião deixando o arquivo da proposta com o cliente (pasta propostas/): "
        "quem vê a própria marca num site novo dificilmente esquece.",
        "Registre o follow-up na sua planilha (leads.csv) — o segundo contato é onde a maioria desiste.",
    ):
        doc.add_paragraph(text, style="List Bullet")

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.add_run("Sugestão de primeira mensagem (WhatsApp):").bold = True
    msg = doc.add_paragraph()
    msg_run = msg.add_run(
        "Olá! Tudo bem? Trabalho com sites para empresas de "
        f"{meta.get('niche', 'do seu ramo')} em {meta.get('place', 'sua região')} e dei uma olhada na presença "
        "online de vocês. Montei uma proposta rápida do que daria para melhorar para trazer mais clientes "
        "pelo celular. Posso te mostrar em 2 minutos?"
    )
    msg_run.italic = True

    # ---- 7. arquivos
    doc.add_heading("7. Arquivos desta pasta", level=1)
    _table(
        doc,
        ["Arquivo / pasta", "O que é"],
        [
            ["relatorio-completo.html", "Tudo num arquivo só: dashboard + diagnósticos + demos"],
            ["relatorio.docx", "Este documento"],
            ["index.html", "Dashboard com filtros (site próprio não localizado, pior nota, sem WhatsApp)"],
            ["leads.csv", "Planilha de leads com notas e links"],
            ["leads.json", "Todos os dados extraídos, inclusive as auditorias"],
            ["propostas/", "Landing page nova de cada empresa (sua demo)"],
            ["briefings/", "Briefing em Markdown para reconstruir o site"],
            ["relatorios/", "Diagnóstico completo de cada site"],
            ["sites/", "Dados brutos da auditoria de cada site"],
        ],
        widths=[2.2, 4.3],
    )

    # ---- 8. limites
    doc.add_heading("8. Observações e limites", level=1)
    for text in (
        "A nota de performance é uma estimativa medida na própria visita (tempo de resposta, peso da página, "
        "requisições), não um laudo de Lighthouse. Para propostas grandes, confirme com o PageSpeed Insights.",
        "A detecção de tecnologia é feita por assinatura e pode haver falso positivo.",
        "Telefones e e-mails são dados públicos: use com finalidade comercial legítima, contato proporcional "
        "e canal de descadastramento.",
        "Sites que não responderam aparecem como 'Não auditado' e não entram na média.",
    ):
        doc.add_paragraph(text, style="List Bullet")

    if meta.get("errors"):
        doc.add_paragraph()
        p = doc.add_paragraph()
        p.add_run("Avisos da coleta:").bold = True
        for err in meta["errors"][:6]:
            doc.add_paragraph(str(err)[:160], style="List Bullet")

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(target))
    return str(target)


# ---------------------------------------------------------------- guia


def write_guide_docx(path: str | Path) -> str:
    """Escreve o guia de uso da ferramenta em .docx."""
    doc = Document()
    _setup(doc)

    h = doc.add_heading("siteaudit — guia de uso", level=0)
    for run in h.runs:
        run.font.color.rgb = ACCENT
    p = doc.add_paragraph()
    run = p.add_run("Descubra empresas por nicho + região, audite o site de cada uma e saia com uma demo pronta "
                    "para apresentar.")
    run.italic = True
    run.font.color.rgb = MUTED

    doc.add_heading("1. O que a ferramenta faz", level=1)
    doc.add_paragraph(
        "Você informa um nicho e uma cidade. Ela levanta as empresas da região, abre o site de cada uma "
        "como um visitante abriria, extrai tudo que importa (conteúdo, SEO, performance, design, tecnologia "
        "e contatos) e gera o material de venda: dashboard, diagnóstico, proposta de site novo e briefing."
    )

    doc.add_heading("2. Como funciona", level=1)
    for text in (
        "Descobre: consulta Google Maps, Bing, DuckDuckGo, OpenStreetMap ou uma planilha sua.",
        "Limpa: remove diretórios e redes sociais, junta duplicados e cruza os dados das fontes.",
        "Audita: baixa cada site (respeitando robots.txt e com pausa entre requisições); se a página voltar "
        "vazia por ser feita em JavaScript, reabre em navegador real automaticamente.",
        "Diagnostica: transforma cada problema em um achado com impacto e solução; a soma vira nota de 0 a 100.",
        "Gera: escreve os arquivos HTML, Markdown, CSV e DOCX na pasta do relatório.",
    ):
        doc.add_paragraph(text, style="List Bullet")

    doc.add_heading("3. O que você precisa", level=1)
    _table(
        doc,
        ["Item", "Necessidade", "Detalhe"],
        [
            ["Python 3.10+", "obrigatório", "Linguagem que roda a ferramenta"],
            ["pip install -r requirements.txt", "obrigatório", "5 bibliotecas leves"],
            ["Chave de API", "NÃO precisa", "Só se quiser a rota oficial do Google"],
            ["Navegador Chromium", "recomendado", "Sites em JavaScript, capturas e Google Maps"],
            ["Google Places API", "opcional", "Rota oficial e estável; tem franquia gratuita"],
            ["Hospedagem", "NÃO precisa", "O resultado é arquivo estático"],
            ["Banco de dados", "NÃO precisa", "Dados ficam em leads.csv e leads.json"],
            ["Cartão de crédito", "NÃO precisa", "Só se ativar a Places API"],
        ],
        widths=[2.0, 1.3, 3.2],
    )

    doc.add_heading("4. Instalação", level=1)
    for line in ("cd siteaudit", "pip install -r requirements.txt", "bash scripts/install_browser.sh",
                 "python3 -m siteaudit providers"):
        par = doc.add_paragraph()
        run = par.add_run(line)
        run.font.name = "Consolas"
        run.font.size = Pt(9.5)
        par.paragraph_format.space_after = Pt(0)
        par.paragraph_format.left_indent = Inches(0.25)

    doc.add_heading("5. Comandos", level=1)
    _table(
        doc,
        ["Comando", "Para quê"],
        [
            ["run --niche X --city Y --state UF", "Pipeline completo: descobrir + auditar + relatório"],
            ["discover ...", "Só levantar os leads"],
            ["audit --url https://site.com.br", "Auditar um site específico"],
            ["audit --file urls.txt", "Auditar uma lista de URLs"],
            ["report --from leads.json", "Regerar o relatório sem nova coleta"],
            ["serve --dir out/pasta", "Abrir o relatório no navegador"],
            ["providers", "Listar as fontes de dados disponíveis"],
        ],
        widths=[2.9, 3.6],
    )
    doc.add_paragraph(
        "Exemplo completo: python3 -m siteaudit run --niche \"prótese capilar\" --city \"Porto Alegre\" "
        "--state RS --providers maps,bing,ddg --limit 20"
    )

    doc.add_heading("6. Como usar o resultado com o cliente", level=1)
    for text in (
        "Revise empresas para as quais nenhum domínio próprio foi localizado; confirme a situação antes de abordar.",
        "Para quem tem site, abra o diagnóstico e mostre os ganhos rápidos.",
        "Mostre a proposta (pasta propostas/): é a landing page nova com as cores e o WhatsApp do cliente.",
        "Use o briefing (pasta briefings/) para mostrar método na reconstrução.",
        "Exporte leads.csv para seu CRM e faça o follow-up.",
    ):
        doc.add_paragraph(text, style="List Bullet")

    doc.add_heading("7. Problemas comuns", level=1)
    _table(
        doc,
        ["Sintoma", "Solução"],
        [
            ["HTML não abre / links não funcionam", "Abra o relatorio-completo.html (arquivo único)"],
            ["maps: lista não carregou", "CAPTCHA ou IP bloqueado: use places, osm ou rode do seu computador"],
            ["ddg: resposta bloqueada", "Muitas consultas seguidas: aumente --delay ou use bing"],
            ["libnspr4.so not found", "Rode scripts/install_browser.sh"],
            ["Nota muito baixa mas site carrega bem", "Site em JavaScript: use --render"],
            ["Muitos HTTP 403", "A hospedagem bloqueia robôs; a ferramenta registra e segue"],
        ],
        widths=[2.9, 3.6],
    )

    doc.add_heading("8. Cuidados", level=1)
    for text in (
        "Raspar buscadores fere os termos do Google e do Bing — para uso comercial recorrente, "
        "prefira a Places API.",
        "Telefone e e-mail são dados pessoais: trate conforme a LGPD.",
        "A nota de performance é estimativa própria, não Lighthouse.",
    ):
        doc.add_paragraph(text, style="List Bullet")

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(target))
    return str(target)
