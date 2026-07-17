# Baita Coin — Documento Técnico para Auditoria

> **Público-alvo:** time de desenvolvimento externo, avaliação de **segurança** e
> **escalabilidade** pré-lançamento.
> **Atualizado:** 17/07/2026 · commit `06a2f1d` · 222 testes · 42 migrations · 77 endpoints

Este documento é o ponto de entrada da auditoria. Complementos no repositório:
- **`README.md`** — como rodar em 4 comandos, mapa de arquitetura, regras de ouro
- **`docs/COMPLIANCE.md`** — dossiê PCI / SUSEP / LGPD com apontadores verificáveis pro código

---

## 1. O que é o sistema

Backend do **Baita Coin**, o sistema de pontos do clube de benefícios **Baita
Benefícios** (Grupo RBS / Diário Gaúcho). O associado compra pacotes de R$20
(PIX avulso ou assinatura no cartão), recebe coins (1 real = 1 coin, taxa
configurável) e números da sorte pro sorteio mensal lastreado em Título de
Capitalização (Modalidade Incentivo, Circular SUSEP 656/2022, apuração pela
Loteria Federal). Os coins são gastos em benefícios de 140+ parceiros (cupom,
cashback, desconto no caixa) e expiram em 90 dias (FIFO por lote).

**Frontends** (fora deste repositório): app do cliente e painel administrativo
(manager), ambos construídos no **Lovable** e consumindo esta API. Para auditar
o frontend, usar o export/GitHub-sync do próprio Lovable — o manager acessa as
rotas `/v1/admin/*` através de um proxy (Supabase Edge Function) que guarda a
API key; o app consome apenas rotas públicas.

## 2. Stack e infraestrutura

| Camada | Tecnologia |
|---|---|
| API | Python 3.9+ · FastAPI · Uvicorn |
| Dados | PostgreSQL (SQLAlchemy Core com SQL explícito `text()` — **sem ORM**) |
| Migrations | Alembic, SQL explícito, execução automática no deploy (CMD do Dockerfile) |
| Deploy | Render (Blueprint `render.yaml`): web service Docker + Postgres gerenciado + cron diário |
| CI implícito | push na `main` → deploy automático; suíte de testes local (pytest) |
| Dependências | mínimas de propósito: fastapi, sqlalchemy, psycopg3, alembic, pydantic v2, requests. Hash de senha via stdlib (pbkdf2) |

## 3. Arquitetura

```
App cliente (Lovable) ──────────┐        Manager (Lovable + proxy c/ API key)
        │ rotas públicas /v1/*  │                │ /v1/admin/*
        ▼                       ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│  API FastAPI (Render)                                       │
│  16 módulos por domínio, cada um com as camadas:            │
│  routes → service → repository → schemas → errors           │
│                                                             │
│  wallet/          ledger, contas, login (senha e OTP)       │
│  capitalizacao/   compras, planos, campanhas, webhook       │
│  pagamentos/      gateway (Pagar.me PIX + assinaturas)      │
│  assinaturas/     cartão recorrente (ciclos via invoice)    │
│  sorteios/        edições, números, apuração auditável      │
│  beneficios/      catálogo, modos de resgate, cupons        │
│  notas_fiscais/   cashback por NF (Infosimples/SEFAZ)       │
│  fiscal/          emissão de NFS-e da venda (NFe.io)        │
│  resgates/        gift cards (reserva→confirmação→débito)   │
│  anuncios/        banners/imagens do app                    │
│  site_config/     aparência do app (rascunho→publicar)      │
│  admin_usuarios/  gestão de cadastros + auditoria imutável  │
│  painel/          dashboard agregado + mecânica dos pontos  │
│  notificacoes/    WhatsApp (mock + Meta Cloud API)          │
│  jobs/            cron de expiração FIFO (diário)           │
│  shared/          dinheiro (Decimal), idempotência          │
└──────────────┬──────────────────────────────────────────────┘
               ▼
        PostgreSQL (Render)
               ▲
        cron diário 06:00 UTC (expiração de lotes)

Integrações externas (padrão adapter, mock por default, real via env):
Pagar.me (PIX ✅ prod · assinaturas ✅ prod) · Infosimples/SEFAZ (✅ prod,
aguardando e-CNPJ p/ RS) · NFe.io (pronto) · Meta WhatsApp Cloud (pronto)
```

**Padrões estruturais** (verificáveis em qualquer módulo; `wallet/` é o canônico):
- `routes.py` traduz HTTP, **zero regra de negócio**; `service.py` orquestra e
  abre transações; `repository.py` só SQL; `schemas.py` Pydantic; `errors.py`
  exceções de domínio → envelope `{erro:{codigo,mensagem,detalhes}}`.
- **Adapter pattern** em toda integração: interface + mock + implementação real
  selecionada por env var. Dev/teste nunca chamam serviço externo.

## 4. Invariantes de dados (o coração da auditoria)

1. **`ledger_events` é append-only.** Trigger no Postgres bloqueia UPDATE/DELETE
   (migration 0003). Saldo = `SUM(coins)`; correção = evento de estorno. O mesmo
   trigger de imutabilidade protege `apuracoes`/`apuracao_contemplados` (sorteio)
   e `admin_usuarios_alteracoes` (trilha de auditoria administrativa).
2. **Toda escrita relevante é idempotente.** `idempotency_key` UNIQUE + padrão
   "tenta inserir → constraint → devolve o existente" (`shared/postgres.py`).
   Webhooks reentregues não creditam em dobro (coberto por teste).
3. **Dinheiro é `Decimal`** com arredondamento centralizado (`shared/dinheiro.py`).
4. **Débito só após confirmação externa** (resgates: reserva → fornecedor
   confirma → débito). Compra credita apenas via webhook do gateway.
5. **Coins expiram por lote FIFO (90 dias)** com `FOR UPDATE` contra concorrência;
   lote vencido é inconsumível pelo relógio (filtro por `data_expiracao` no
   SELECT), não dependendo do horário do cron.
6. **Números da sorte**: aleatórios, únicos por série de 100.000 (regra 3.1.4 do
   regulamento), emissão com `ON CONFLICT DO NOTHING` + retry. Apuração reproduz
   o método oficial da Loteria Federal e grava resultado **imutável com hash
   SHA-256** de integridade (`sorteios/apuracao.py` — validado contra o exemplo
   do próprio regulamento).

## 5. Modelo de segurança

| Superfície | Proteção |
|---|---|
| `/v1/*` públicas (app) | CORS aberto (pré-lançamento; restringir ao domínio real no go-live), validação Pydantic, envelope de erro sem stack trace |
| `/v1/admin/*` e `/v1/internal/*` | Header `X-Internal-Api-Key` (middleware; sem a env var setada, desliga — só para dev/teste local) |
| `/v1/webhooks/pagarme` | Token compartilhado via header ou Basic auth; **fechado por padrão** se a env não existir |
| Cartão de crédito | **Nunca toca o backend** (PCI): app tokeniza direto na Pagar.me com chave pública; armazenamos só bandeira + últimos 4 |
| Senhas | pbkdf2-sha256 (260k iterações, salt por senha), stdlib |
| OTP (login por código) | código hasheado, expira 5 min, máx. tentativas, rate limit anti-flood, enviado só pro celular já cadastrado |
| Dados pessoais (LGPD) | consentimento por conta com carimbo de data; export de base **sem CPF** (minimização); auditoria imutável de alterações administrativas |
| Headers | nosniff, X-Frame-Options DENY, HSTS, Referrer-Policy em toda resposta |
| Segredos | somente env vars no Render; `.env` gitignored; repositório auditado sem segredos |
| Logs | nunca registram payload de cartão/código OTP; erros de gateway logam só mensagens |

### ⚠️ Gap conhecido nº 1 (declarado, prioritário antes do go-live)
**Não há autenticação por sessão/token nas rotas client-facing**: elas validam
que o `account_id` existe, mas não que o chamador é o dono da conta. Aceitável
em beta fechado; **obrigatório** implementar (JWT/sessão + rate limiting +
CORS restrito) antes de escala pública. Este é o item nº 1 de `docs/COMPLIANCE.md`
e deve ser o primeiro foco da auditoria de segurança.

## 6. Escalabilidade — decisões e dívidas conscientes

Detalhadas com plano em `docs/COMPLIANCE.md` (seção 5). Resumo priorizado:

1. 🔴 Autenticação por usuário (acima).
2. 🔴 **Postgres em plano free no Render** (`render.yaml`): subir para plano pago
   (backup/PITR, sem prazo de validade) antes de operação real.
3. 🟡 Processamento assíncrono usa `BackgroundTasks` in-process; services já são
   independentes de framework — migrar para fila (worker) é mover a chamada.
4. 🟡 Imagens em `bytea` no Postgres (volume atual ok); contrato é URL — trocar
   para object storage não afeta frontends.
5. 🟢 Saldo por SUM (correto e auditável; materializar só se virar gargalo).
6. 🟢 Virada automática de série do sorteio ao passar de 100.000 números.

Pontos fortes para escala: sem estado no processo (scale-out horizontal trivial),
locks pontuais (`FOR UPDATE SKIP LOCKED` no estoque de cupons), índices cobrindo
as consultas quentes, throttling onde há custo por chamada (reconsulta SEFAZ).

## 7. Qualidade

- **222 testes** (integração contra Postgres real + unitários de motores puros),
  ~4.100 linhas de teste para ~10.200 de código. Rodam em ~15 s.
- Motores críticos são **funções puras testadas isoladamente**: conversão de
  coins, alocação FIFO, apuração do sorteio (validada contra o exemplo numérico
  do regulamento SUSEP), parser de QR de NFC-e.
- Testes de regressão para todos os bugs reais encontrados em produção (ex.:
  assinatura órfã travando conta; lote vencido consumível antes do cron;
  contagem de tentativas OTP desfeita por rollback).
- Lint: ruff (F/E9/I) limpo.
- Convenção de commits descritiva com o "porquê" — `git log` serve de changelog.

## 8. Inventário de endpoints (77)

Gerado do código; a fonte da verdade é `/docs` (OpenAPI) da própria API.

- **Públicos (32)** — app do cliente: contas/login/OTP/busca por CPF-ou-celular,
  saldo/números da sorte/assinatura da conta, compras + planos + campanhas,
  benefícios (lista/detalhe/usar), notas fiscais (submeter/status), resgates,
  anúncios, sorteio vigente, site-config, config de pagamentos, webhook Pagar.me
  (token), health.
- **Admin (40)** — manager: dashboard, mecânica dos pontos, usuários (CRUD +
  exclusão restrita + export CSV + reset de teste), planos, benefícios (+ modos
  de resgate + estoque de cupons), campanhas, sorteios (edições + apuração
  simular/executar/consultar), notas fiscais (fila) + parceiros/regras, NFS-e
  (reemitir), anúncios (+ upload), site-config (rascunho/publicar/histórico).
- **Internos (5)** — serviço-a-serviço: eventos de ledger, sorteios, webhook
  interno de pagamento.

## 9. Roteiro sugerido para a auditoria

1. `README.md` → rodar local (`docker compose up -d` + pytest) — suíte verde.
2. `docs/COMPLIANCE.md` → conferir cada afirmação contra o código apontado.
3. Segurança: começar pelo Gap nº 1 (seção 5) e pela superfície pública (OpenAPI).
4. Dados: migrations 0001–0003 (ledger), 0034 (apuração imutável), 0040 (auditoria admin).
5. Fluxos de dinheiro: `capitalizacao/service.py::processar_webhook_pagamento`
   (idempotência), `assinaturas/service.py` (ciclos), `resgates/service.py`
   (reserva→confirmação→débito), `jobs/expirar_lotes.py` (expiração).
6. Escalabilidade: seção 6 + índices nas migrations.

## 10. Backlog de produto (contexto)

WhatsApp Cloud (adapter pronto; falta app/template na Meta) · gift cards (motor
pronto; falta parceiro) · e-CNPJ A1 para NFC-e no RS · responsivo/push/e-mail
(backend pronto) · Pix Automático (depende Pagar.me) — detalhes no arquivo
`BACKLOG - pendências Baita.md` mantido pelo product owner.
