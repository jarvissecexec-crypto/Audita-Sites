# Arquitetura Fase 2 (explicação objetiva)

## 1) Camada `storage/` (abstração de persistência)
É um "contrato" único para salvar e ler dados, sem acoplar o sistema a um banco específico.

Na prática:
- o pipeline chama `storage.save_lead(...)`
- tanto faz se por trás está SQLite local ou Supabase

Benefícios:
- troca de banco sem reescrever o pipeline
- testes mais fáceis
- evolução futura mais segura

---

## 2) `sqlite_store` + `supabase_store`
São implementações concretas da camada acima:

- `sqlite_store`: mantém compatibilidade local/offline
- `supabase_store`: grava no Postgres do Supabase para centralizar histórico

Você pode usar os dois ao mesmo tempo (local + nuvem).

---

## 3) Comando `sync` (SQLite -> Supabase)
Serve para migrar o que já foi coletado localmente para o Supabase.

Exemplo de uso futuro:
`python -m siteaudit sync --from-sqlite data/siteaudit.sqlite3`

Benefícios:
- não perde histórico antigo
- transição gradual

---

## 4) Módulo `intel/` (pesquisa digital da empresa)
Módulo de enriquecimento comercial para cada lead.

Coleta:
- redes sociais oficiais (instagram, facebook, linkedin, youtube...)
- diretórios públicos
- citações/menções na web
- consistência de NAP (nome/endereço/telefone)

Entrega:
- `digital_footprint_score`
- evidências (URLs e fontes)

---

## 5) Chaves Supabase (novo padrão)
Para evitar confusão, neste projeto vamos usar:

- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY`

E **não** vamos usar:
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_ANON_KEY`

Regras:
- backend local (worker/sync): usar `SUPABASE_SECRET_KEY`
- frontend/painel público: usar `SUPABASE_PUBLISHABLE_KEY`
