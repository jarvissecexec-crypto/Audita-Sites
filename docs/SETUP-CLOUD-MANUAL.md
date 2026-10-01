# Setup cloud manual (estritamente necessário)

As integrações diretas via API falharam neste ambiente por permissão/autenticação do lado das ferramentas MCP.
Então, estes são os únicos passos manuais obrigatórios agora:

## 1) Supabase
1. Abra seu projeto no painel Supabase.
2. Rode SQL Editor com:
   - `infra/supabase/migrations/001_initial_internal_stack.sql`
3. Garanta as env vars locais:
   - `SUPABASE_URL`
   - `SUPABASE_SECRET_KEY`
   - `SUPABASE_PUBLISHABLE_KEY`

## 2) GitHub
1. Crie o repositório `Audita-Sites` no owner `jarvissecexec-crypto` (se ainda não existir).
2. Faça push desta pasta local para `main`.
3. Verifique se o workflow `ci.yml` foi executado.

## 3) Vercel
1. Crie o projeto `Audita-Sites`.
2. Conecte ao repositório GitHub.
3. Configure as env vars do projeto:
   - `SUPABASE_URL`
   - `SUPABASE_PUBLISHABLE_KEY`

Após isso, o restante do desenvolvimento segue automático no código.
