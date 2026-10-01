# siteaudit

**Ferramenta interna para prospecção, diagnóstico técnico de sites e priorização de leads.**

> Nota: este projeto foi reposicionado para uso interno. A geração automática de propostas/preview pode ser desativada com `--internal-only`.

## Início rápido (Windows)

```powershell
./scripts/setup.ps1
./scripts/start_admin.ps1
```

## Modo interno (sem gerar propostas/briefings)

```bash
python -m siteaudit run --niche "pizzaria" --city "Igrejinha" --state RS --providers bing,ddg,maps --internal-only
```

## Documentação de implementação

- Checklist de execução: `docs/CHECKLIST-IMPLEMENTACAO.md`
- Migração inicial Supabase: `infra/supabase/migrations/001_initial_internal_stack.sql`
- Arquivos antigos/legado: `docs/legacy/`
- Setup cloud manual (somente bloqueios de permissão): `docs/SETUP-CLOUD-MANUAL.md`


Feito para quem vende sites: você escolhe um nicho ("pizzaria") e uma região
("Igrejinha / RS"), a ferramenta levanta os negócios locais, analisa o site de cada
um (SEO, performance, design, conteúdo, tecnologia e conversão) e gera:

| Saída | Para que serve |
|---|---|
| `index.html` | Dashboard com leads, filtros (site próprio não localizado, pior nota, sem WhatsApp…) e achados |
| `relatorios/<empresa>.html` | Diagnóstico completo do site — o que você mostra na reunião |
| `propostas/<empresa>.html` | **Landing page nova, moderna e responsiva**, já com as cores, textos, telefone e fotos do cliente |
| `briefings/<empresa>.md` | Briefing em Markdown para (re)construir o site em qualquer ferramenta/IA |
| `leads.csv` / `leads.json` | Dados brutos para planilha, CRM ou outro pipeline |
| `sites/<empresa>.json` | Tudo que foi extraído, campo a campo |

---

## 1. Instalação

```bash
cd siteaudit
bash scripts/setup.sh                    # cria .venv e instala dependências sem alterar o Python do sistema

# navegador real — necessário para sites em JavaScript, capturas de tela e Google Maps
bash scripts/install_browser.sh          # funciona SEM root (ver observação abaixo)
```

> **Sem root?** O script baixa os `.deb` das dependências do Chromium e extrai em
> `~/.local/lib/chromium-deps`. O `siteaudit` adiciona esse diretório ao
> `LD_LIBRARY_PATH` automaticamente antes de abrir o navegador.
> Se você tiver `sudo`, `sudo playwright install-deps chromium` resolve em um passo.

Confira se está tudo certo:

```bash
python3 -m siteaudit providers     # lista os provedores de descoberta
python3 -m siteaudit --version
```

### Abrir o painel administrativo

```bash
bash scripts/start_admin.sh
# o painel abre no navegador; URL local: http://127.0.0.1:8765
```

Para os demais comandos, use o interpretador do ambiente criado: `./.venv/bin/python -m siteaudit ...`

O painel permite criar buscas com **tipo de empresa e localidades livres**, escolher
provedores, definir quantidade total ou por localidade, acompanhar execuções e
administrar etapas comerciais e notas dos leads. O histórico fica em
`data/siteaudit.sqlite3`; para trocar o local, defina `SITEAUDIT_DB` antes de iniciar.
Por segurança, o painel desta versão aceita somente conexões da própria máquina.

> A auditoria de sites é opcional por busca e limitada pelo número definido no painel.
> Alguns provedores fazem scraping de páginas públicas e podem ter restrições de uso;
> confira os termos de cada fonte antes de usá-los de forma recorrente.

---

## 2. Uso

### Pipeline completo (descobrir → auditar → relatório)

```bash
python3 -m siteaudit run \
  --niche "pizzaria" --city "Igrejinha" --state RS \
  --providers bing,ddg,maps --limit 25 --max-audit 40
```

### Só descobrir leads

```bash
python3 -m siteaudit discover --niche "contador" --city "Novo Hamburgo" --state RS \
  --providers maps --limit 30 --csv leads.csv
```

### Auditar sites que você já tem

```bash
# uma ou mais URLs
python3 -m siteaudit audit --url https://exemplo.com.br --city Gramado --state RS

# arquivo com uma URL por linha
python3 -m siteaudit audit --file urls.txt --out-dir out --name meus-clientes

# CSV/JSON de leads (aceita as colunas nome, site, telefone, endereço, cidade, uf, categoria)
python3 -m siteaudit run --niche "meus leads" --providers manual --file exemplos/leads-exemplo.csv
```

### Ver o relatório no navegador

```bash
python3 -m siteaudit serve --dir relatorios/demo-completa --port 8080
# ou simplesmente abra relatorios/demo-completa/index.html
```

### Outras opções úteis

| Flag | Efeito |
|---|---|
| `--render` | Usa navegador real em **todos** os sites (mais lento, mais fiel) |
| `--screenshots` | Salva captura da home em `assets/` |
| `--fast` | Não mede o tamanho dos assets (bem mais rápido) |
| `--concurrency N` | Sites auditados em paralelo (padrão 6) |
| `--delay 1.5` | Espera entre requisições no mesmo host (educado; use ≥1 se for raspar muito) |
| `--no-auto-render` | Desliga o fallback automático para navegador em sites vazios |
| `--no-badge` | Remove o selo "proposta de demonstração" da demo |
| `--ignore-robots` | Ignora `robots.txt` (só para sites seus/autorizados) |
| `--places-key KEY` | Chave da Google Places API (ou `export GOOGLE_MAPS_API_KEY=...`) |

---

## 3. Provedores de descoberta

| Provider | Como funciona | Prós | Contras |
|---|---|---|---|
| `maps` | Google Maps via navegador | **Melhor qualidade**: nome, telefone, endereço, nota e nº de avaliações | Frágil: o Google pode exigir CAPTCHA e bloquear IPs de datacenter |
| `places` | Google Places API (conector Legacy no CLI) | Fonte oficial; cobrança por uso | Precisa de chave e faturamento; **pausado no painel até migração e controle de custos** |
| `bing` | Busca web do Bing | Sem chave, boa cobertura local | Pode servir resultados enviesados conforme o IP |
| `ddg` | DuckDuckGo HTML | Sem chave | Anti-bot: bloqueia depois de algumas consultas seguidas |
| `google` | Busca do Google via navegador | Maior cobertura | CAPTCHA frequente |
| `osm` | OpenStreetMap (Nominatim + Overpass) | Gratuito, sem bloqueio, sem chave | Cobertura irregular no Brasil (boa em cidades turísticas/grandes) |
| `manual` | Seu CSV/JSON | Total controle | Você precisa da lista |

**Recomendação prática:**

- Escolha fontes com termos compatíveis com seu uso e respeite os limites de cada uma.
- OSM é gratuito, mas tem cobertura irregular; provedores de SERP e scraping de Maps podem restringir automação.
- A integração Places existente usa endpoints Legacy e precisa ser migrada e ter limites de custo antes de ser habilitada no painel.

A ferramenta **nunca quebra** se um provedor falhar: ela registra o aviso no relatório
e segue com os demais.

---

## 4. O que é extraído de cada site

- **Conteúdo**: h1–h6, parágrafos, listas (serviços/produtos), FAQ, contagem de palavras, termos mais frequentes
- **SEO**: title, meta description, canonical, robots, viewport, idioma, Open Graph, hreflang, sitemap.xml, robots.txt, HTTPS, JSON-LD/Schema.org
- **Design**: paleta de cores (com contraste WCAG), fontes, tamanhos, raios de borda, seções detectadas (hero, serviços, depoimentos, FAQ, contato, mapa), CTAs, menu fixo, Grid/Flex
- **Performance**: duração da requisição HTTP (não TTFB), peso estimado, nº de requisições, recursos bloqueantes, imagens sem lazy load, arquivos > 250 KB, domínios de terceiros, nota A–E
- **Tecnologia**: CMS, page builder, frameworks, analytics, pixels, chat, servidor/CDN, segurança, fontes, mapas, pagamento, formulários/CRM
- **Conversão**: telefones, WhatsApp, e-mails, formulários, redes sociais, endereço, CEP, horários, mapa incorporado
- **Páginas internas**: visita contato/sobre/serviços/produtos para enriquecer os dados

### Como a nota é calculada

Cada achado tem um peso por gravidade (crítico 22, alto 12, médio 6, baixo 2).
A soma vira nota por **decaimento exponencial**. É uma heurística técnica baseada
no HTML e nos recursos observados; **não mede conversão, não prova qualidade comercial
e não deve ser usada sozinha para decidir prioridade de abordagem**.

- **85–100** — poucos achados ponderados nesta análise
- **70–84** — alguns achados ponderados nesta análise
- **50–69** — vários achados ponderados; revisar as evidências
- **< 50** — muitos achados ponderados; validar os resultados antes de qualquer afirmação
- **Site próprio não localizado** — sinal para revisar; não prova que a empresa não tenha site

---

## 5. Estrutura de saída

```
relatorios/<nicho>-<cidade>-<hhmm>/
├── index.html              # dashboard (filtros + ordenação + links)
├── leads.csv               # uma linha por empresa
├── leads.json              # tudo, incluindo as auditorias completas
├── relatorios/<slug>.html  # diagnóstico do site
├── propostas/<slug>.html   # landing page de demonstração
├── briefings/<slug>.md     # briefing para reconstrução
├── sites/<slug>.json       # dados brutos da auditoria
└── assets/<slug>.png       # capturas (com --screenshots)
```

---

## 6. Como vender com isso (roteiro de 10 minutos)

1. Abra o **dashboard** e filtre por **"Site não localizado"** — confirme a situação antes de abordar.
2. Para quem tem site, abra o **relatório** e leve os **ganhos rápidos** (críticos e altos).
3. Mostre a **proposta** (`propostas/<empresa>.html`): a landing page nova, com as cores,
   textos e fotos reais dele, WhatsApp clicável e seções de conversão.
4. Feche com o **briefing** (`briefings/<empresa>.md`): mostra que você tem método, não
   só um template.
5. Exporte `leads.csv` para o seu CRM e registre o follow-up.

O briefing já vem com um **copy de primeiro contato** pronto no final.

---

## 7. Boas práticas, limites e ética

- A auditoria dos sites consulta `robots.txt` por padrão e aplica delay. Isso não substitui
  os termos próprios dos provedores de descoberta. Use `--delay 1.5` ou mais em varreduras grandes.
- Scraping de buscadores pode ferir os termos dos provedores. **Para uso comercial
  recorrente, prefira APIs oficiais e fontes autorizadas**; o conector Places atual ainda é Legacy.
- Os dados coletados são públicos, mas telefone/e-mail são dados pessoais: no Brasil,
  trate conforme a **LGPD** — finalidade legítima, contato proporcional e opt-out simples.
- A nota de performance é uma **heurística** da própria visita (duração da resposta,
  peso estimado e recursos), não um Lighthouse completo. A duração inclui a transferência
  do corpo e não equivale a TTFB. Use ferramentas laboratoriais para propostas grandes.
- A detecção de tecnologia é por assinatura: pode haver falso positivo/negativo.

---

## 8. Solução de problemas

| Sintoma | Causa provável | Saída |
|---|---|---|
| `maps: lista de resultados não carregou` | CAPTCHA ou IP de datacenter bloqueado | Use `--providers places` (com chave) ou rode de um IP residencial; o `osm` também ajuda |
| `ddg: resposta bloqueada (anti-bot)` | Muitas consultas seguidas | Aumente `--delay`, reduza `--limit`, ou use `bing`/`maps` |
| Bing devolve resultados sem relação | SERP servida para outra região/IP | A ferramenta já filtra por relevância; combine com `maps` |
| `Chromium ... libnspr4.so not found` | Faltam libs do sistema | Rode `bash scripts/install_browser.sh` |
| Site aparece com nota muito baixa mas carrega bem | Site é todo em JS e o HTTP devolve só o cascaço | Use `--render` (navegador real) |
| HTTP 403 em vários sites | Hospedagem bloqueia o IP do sandbox/datacenter | Rode da sua máquina; o 403 é registrado como "Não auditado" |

---

## 9. Estrutura do código

```
siteaudit/
├── cli.py                  # comandos: run, discover, audit, report, serve, providers
├── models.py               # Lead e Finding
├── admin/                  # painel local, API administrativa, SQLite e workers de busca
├── discovery/              # provedores de descoberta (bing, ddg, google, maps, places, osm, manual)
├── audit/                  # extração e diagnóstico
│   ├── runner.py           # orquestra a auditoria de um site
│   ├── extract.py          # conteúdo, contatos, links, imagens, formulários, schema.org
│   ├── seo.py  design.py  perf.py  tech.py  scoring.py
├── report/                 # templates Jinja + gerador de CSV/JSON/HTML/Markdown
└── utils/                  # cliente HTTP (robots, rate limit, Playwright) e helpers de texto
```

Para estender:

- **Nova assinatura de tecnologia**: adicione uma tupla em `SIGNATURES` (`audit/tech.py`)
- **Novo provedor**: crie uma classe herdando `BaseProvider` e registre em `discovery/__init__.py`
- **Outro tipo de relatório**: adicione um template em `report/templates/` e uma chamada em `report/generator.py`

---

## 10. Exemplo incluído

```bash
python3 -m siteaudit run \
  --niche "Pizzarias e contadores" --city "Igrejinha / Novo Hamburgo / Gramado" --state RS \
  --providers manual --file exemplos/leads-exemplo.csv --name demo-completa
```

O resultado deste comando está em `relatorios/demo-completa/` — abra o `index.html`.
