# Checklist de Implementação (Interno)

## 1) O que o agente já fez
- [x] Estrutura base de pastas criada (`docs/`, `infra/supabase/migrations/`, `.github/workflows/`)
- [x] Artefatos antigos movidos para `docs/legacy/`
- [x] Pasta `relatorios/` limpa e preparada com `.gitkeep`
- [x] CI inicial no GitHub Actions
- [x] Modo `--internal-only` implementado (não gera propostas/briefings automáticos)
- [x] Migração SQL inicial do Supabase criada

## 2) O que o agente vai fazer na próxima etapa de desenvolvimento
- [ ] Criar camada de persistência abstrata (`storage/base.py`)
- [ ] Implementar `storage/sqlite_store.py` (adaptando código atual do admin/db)
- [ ] Implementar `storage/supabase_store.py`
- [ ] Criar comando `sync` para enviar histórico SQLite -> Supabase
- [ ] Criar módulo `intel/` para presença digital (redes, diretórios, menções)
- [ ] Implementar `priority_score` e `priority_tier` no pipeline
- [ ] Atualizar painel admin para exibir prioridade comercial

## 3) O que você precisa fazer (manual inevitável)

### GitHub
- [ ] Criar repositório remoto no GitHub e conectar este projeto
- [ ] Enviar o primeiro push (branch principal)

### Supabase
- [ ] Criar projeto no Supabase
- [ ] Executar a migration `infra/supabase/migrations/001_initial_internal_stack.sql`
- [ ] Gerar as credenciais:
  - [ ] `SUPABASE_URL`
  - [ ] `SUPABASE_PUBLISHABLE_KEY`
  - [ ] `SUPABASE_SECRET_KEY`

### Vercel (fase seguinte)
- [ ] Criar projeto Vercel para dashboard de leitura
- [ ] Configurar variáveis de ambiente do Supabase no projeto da Vercel

### APIs opcionais (melhoram a qualidade)
- [ ] `GOOGLE_MAPS_API_KEY` (Places oficial)
- [ ] `PAGESPEED_API_KEY` (PageSpeed Insights)
- [ ] `SERPAPI_KEY` (se optar por provedor oficial de SERP)

## 4) Ferramentas e stack recomendada

### Obrigatórias
- Python 3.12+
- Playwright + Chromium
- Supabase
- GitHub

### Recomendadas
- Vercel (dashboard)
- Postman/Insomnia (testes de API)
- DBeaver (inspeção do banco)

### MCPs / plugins / extensões
- MCP Supabase (já disponível aqui para automações de DB)
- Extensão Python (VS Code)
- EditorConfig + Prettier (para arquivos web do painel)

## 5) Variáveis de ambiente alvo
- `SITEAUDIT_DB` (fallback local SQLite)
- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY`
- `GOOGLE_MAPS_API_KEY` (opcional)
- `PAGESPEED_API_KEY` (opcional)

## 6) Critério de pronto da fase 1
- [ ] Rodar busca + auditoria local
- [ ] Persistir localmente e no Supabase
- [ ] Listar e priorizar leads por score/tier
- [ ] CI verde no GitHub
