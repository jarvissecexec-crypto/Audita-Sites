"""siteaudit — descoberta de leads por nicho/região + auditoria completa de sites.

Fluxo:
    1. discover  -> busca empresas de um nicho em uma cidade/UF (DDG, Bing, Maps, Places API, CSV)
    2. audit     -> extrai conteúdo, SEO, stack técnico, design tokens, performance e contatos
    3. report    -> gera CSV/JSON + dashboard HTML + briefing .md + proposta de demo por site
"""

__version__ = "1.0.0"
