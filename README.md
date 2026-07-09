# Baita Coin — Backend

API do clube de benefícios: carteira de pontos (Baita Coins), sorteios,
catálogo de benefícios, nota fiscal, resgates, anúncios e painel
administrativo. **FastAPI + PostgreSQL**, em produção no Render:
`https://baita-coin-api.onrender.com` (docs interativas em `/docs`).

## Como rodar localmente

```bash
# 1. Postgres (docker) — cria também o banco de teste
docker compose up -d

# 2. Ambiente Python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Migrations + servidor
cp .env.example .env
alembic upgrade head
uvicorn baita_coin.main:app --reload --app-dir src

# 4. Testes (usa o banco baita_coin_test do docker compose)
pytest
```

## Arquitetura em uma tela

```
src/baita_coin/
├── main.py            # app factory, CORS, middleware de API key, handlers de erro
├── config.py          # todas as variáveis de ambiente (Settings)
├── db.py              # engine SQLAlchemy
├── shared/            # helpers usados por todos os módulos
│   ├── dinheiro.py    #   arredondar_centavos (Decimal, nunca float)
│   └── postgres.py    #   constraint_violada (padrão de idempotência)
│
│   # ---- módulos de domínio (todos seguem o mesmo layout) ----
├── wallet/            # contas, ledger de coins, lotes FIFO, login/senha
├── capitalizacao/     # compras, planos, sorteios, campanhas, gateway de pagamento
│   └── apuracao.py    #   apuração auditável do sorteio (método SUSEP, puro)
├── beneficios/        # catálogo desconto/cashback (custo em coins por uso)
├── notas_fiscais/     # cashback por NF de parceiro (QR/OCR/SEFAZ + antifraude)
├── resgates/          # troca de coins por produtos (reserva → confirmação → débito)
├── anuncios/          # espaços de mídia do app (slots livres) + upload de imagens
├── site_config/       # aparência do app editada pelo manager (rascunho → publicar)
├── admin_usuarios/    # listagem/detalhe/tags de usuários pro painel
├── fiscal/            # emissão de NFS-e da venda (NFe.io)
├── notificacoes/      # WhatsApp (senha temporária, avisos)
└── jobs/              # expirar_lotes (cron diário)
```

**Layout padrão de cada módulo** (`wallet/` é o exemplo canônico):

| Arquivo | Responsabilidade | Regra |
|---|---|---|
| `routes.py` | endpoints FastAPI, tradução HTTP | zero regra de negócio |
| `service.py` | regra de negócio + **transações** | abre `engine.begin()`, nunca o repository |
| `repository.py` | SQL puro (SQLAlchemy Core `text()`) | zero regra de negócio |
| `schemas.py` | Pydantic de request/response | validações de formato aqui |
| `errors.py` | exceções de domínio → envelope `{erro:{codigo,mensagem,detalhes}}` | |
| `*_adapter.py` | integrações externas (interface + mock + real) | trocável por env var |

## As 5 regras de ouro (não negociáveis)

1. **`ledger_events` é append-only.** Nunca UPDATE/DELETE — um trigger no
   Postgres bloqueia até SQL manual. Erro se corrige com evento de `estorno`.
   Saldo é sempre `SUM(coins)`, nunca um campo editável.
2. **Toda escrita idempotente.** Endpoints de efeito exigem
   `idempotency_key`; a garantia real é a constraint UNIQUE + o padrão
   "tenta inserir → constraint estourou → devolve o existente"
   (`shared/postgres.constraint_violada`).
3. **Dinheiro é `Decimal`, nunca float.** Arredondamento só via
   `shared/dinheiro.arredondar_centavos`.
4. **Débito só após confirmação externa.** Resgate reserva → fornecedor
   confirma → só então grava o débito. Compra credita só via webhook.
5. **Coins expiram por lote (FIFO, 90 dias).** Todo crédito cria um
   `lote_creditos`; débitos consomem do mais antigo (`FOR UPDATE` contra
   concorrência). O cron `jobs/expirar_lotes.py` roda diariamente.

## Segurança das rotas

- `/v1/*` público (app do cliente) — CORS liberado, sem chave.
- `/v1/internal/*` e `/v1/admin/*` — exigem header `X-Internal-Api-Key`
  igual a `INTERNAL_API_KEY` (sem a env var setada, a checagem desliga —
  proposital para dev/teste local).
- `/v1/webhooks/pagarme` — público, mas exige o token via header
  `X-Webhook-Token` ou como senha do Basic auth do dashboard do Pagar.me.

## Integrações externas (adapter pattern)

Cada integração tem interface + mock + (quando fechada) implementação real,
selecionada por variável de ambiente. **Sem as env vars, tudo roda em mock**
— dev e testes nunca dependem de serviço externo.

| Integração | Adapter | Status | Ativação |
|---|---|---|---|
| Pagamento PIX | `capitalizacao/gateway_pagarme.py` | **real, em produção** | `GATEWAY_PROVIDER=pagarme` + `PAGARME_SECRET_KEY` + `PAGARME_WEBHOOK_TOKEN` |
| Cartão recorrente | `capitalizacao/gateway_pagarme.py` (Subscriptions) | **pronto** | mesmas acima + `PAGARME_PUBLIC_KEY` (tokenização no app) |
| NFS-e da venda | `fiscal/adapter.py` (NFe.io) | pronto, aguardando código municipal | `NFE_PROVIDER=nfeio` + `NFEIO_API_KEY` + `NFEIO_COMPANY_ID` |
| WhatsApp | `notificacoes/whatsapp.py` | mock (loga a mensagem) | implementar adapter da API oficial |
| SEFAZ (NF parceiro) | `notas_fiscais/sefaz_adapter.py` (Infosimples) | **pronto** | `SEFAZ_PROVIDER=infosimples` + `INFOSIMPLES_TOKEN` |
| OCR de nota | `notas_fiscais/ocr_adapter.py` | mock (tudo → revisão manual) | contratar serviço de OCR |
| Fornecedor de resgate | `resgates/provider_adapter.py` | mock | fechar agregador de catálogo |
| Cupom/link afiliado | `beneficios/adapter.py` | mock | fechar rede de afiliados |

## Variáveis de ambiente

Ver `.env.example` e `config.py` (fonte da verdade). Resumo: `DATABASE_URL`
(aceita `postgresql://` de provedores gerenciados — o driver psycopg3 é
forçado), `INTERNAL_API_KEY`, `CORS_ALLOW_ORIGINS`, `PUBLIC_BASE_URL`,
mais as de integração da tabela acima.

## Migrations

Alembic com SQL explícito (`op.execute`), sem autogenerate — cada migration
documenta a decisão no docstring. Rodam automaticamente no deploy
(`alembic upgrade head` no CMD do Dockerfile, antes do uvicorn).

```bash
alembic upgrade head            # aplicar
alembic revision -m "descricao" # criar nova (numerar sequencialmente)
```

## Deploy

Render via Blueprint (`render.yaml`): web service (Docker) + Postgres +
cron do job de expiração. Push na `main` do GitHub → deploy automático.
O frontend (app do cliente e painel) vive no Lovable e consome esta API.

## Scripts utilitários

- `scripts/seed_beneficios.py` — semeia os 140 parceiros do catálogo
- `scripts/importar_logos_beneficios.py` — importa logos/capas do CDN antigo
- `scripts/run-expiracao` → `python -m baita_coin.jobs.expirar_lotes`

## Notas de escala (dívidas conscientes, em ordem de prioridade)

1. **Autenticação por usuário**: rotas client-facing validam o `account_id`
   mas não exigem sessão/token — ok pré-lançamento, obrigatório antes de
   escala. Adicionar rate-limit na busca por CPF junto.
2. **Fila de mensagens**: processamento assíncrono usa BackgroundTasks
   (in-process). As funções de service já são independentes do framework —
   migrar para worker/fila é mover a chamada.
3. **Imagens em object storage**: banners/logos hoje em bytea no Postgres
   (adequado ao volume atual). O contrato é URL — trocar o destino do
   upload não afeta os frontends.
4. **Saldo por SUM**: correto e auditável; se virar gargalo com volume,
   a spec prevê materialized view/cache — nunca saldo editável.
