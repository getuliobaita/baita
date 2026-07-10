# Baita Coin — Dossiê de Compliance e Escalabilidade

Material de apoio para análise de compliance e análise técnica. Cada
afirmação abaixo é verificável no código/banco — as referências apontam o
arquivo ou a migration que a implementa.

## 1. Dados de cartão (PCI-DSS)

**O backend nunca recebe, processa ou armazena dados de cartão.**

- O app tokeniza o cartão **direto na Pagar.me** (certificada PCI-DSS)
  usando a chave pública; o backend recebe apenas um `card_token` de uso
  único que expira em ~60 segundos (`assinaturas/schemas.py`).
- Persistimos somente bandeira e últimos 4 dígitos (`migrations/0039`),
  exatamente o que o PCI permite para exibição.
- Não existe nenhum campo de número de cartão, CVV, validade ou nome do
  portador em nenhuma tabela ou schema (verificável por busca no código).
- Logs nunca registram payloads enviados ao gateway — apenas mensagens de
  erro truncadas (`pagamentos/gateway_pagarme.py`).

## 2. Integridade financeira (SUSEP / auditoria)

- **Ledger append-only**: `ledger_events` não aceita UPDATE nem DELETE —
  um trigger no próprio Postgres bloqueia, mesmo por SQL manual
  (`migrations/0003`). Correção de erro = evento de estorno. Saldo é sempre
  `SUM(coins)`, nunca um campo editável.
- **Idempotência em toda escrita**: constraint UNIQUE + padrão
  "tenta inserir → constraint → devolve o existente". Webhooks reentregues
  nunca creditam em dobro (coberto por testes).
- **Apuração do sorteio auditável**: reproduz o método do regulamento
  (Circular SUSEP 656/2022) a partir dos 5 prêmios da Loteria Federal;
  registro imutável (trigger, `migrations/0034`) com hash SHA-256 de
  integridade — um auditor recalcula o hash com os mesmos dados de entrada
  e confere que nada foi adulterado (`sorteios/service.py`). A apuração
  oficial é da sociedade de capitalização (VIACAP); este ambiente confere.
- **Números da sorte**: aleatórios em [00.000, 99.999], únicos por série de
  100.000 (constraint no banco), conforme regra 3.1.4 do regulamento.
- **Trilha administrativa**: toda criação/edição/exclusão de cadastro pelo
  painel fica em `admin_usuarios_alteracoes`, tabela imutável
  (`migrations/0040`).

## 3. Dados pessoais (LGPD)

Dados armazenados por finalidade:

| Dado | Finalidade | Onde |
|---|---|---|
| CPF | identidade da conta, título de capitalização, NFS-e | `wallet_accounts` |
| Nome, e-mail, celular | contato, cobrança, contato com ganhador | `wallet_accounts` |
| Endereço | NFS-e da venda | `wallet_accounts` |
| Data de nascimento | elegibilidade (16+, regulamento) | `wallet_accounts` |
| Senha | autenticação — armazenada só como hash PBKDF2 | `wallet_accounts.senha_hash` |

- Exclusão: contas **sem** movimentação financeira podem ser excluídas
  fisicamente pelo painel; contas com movimentação têm o histórico
  financeiro preservado por obrigação de auditoria (base legal:
  cumprimento de obrigação regulatória) — a conta é bloqueada.
- Acesso administrativo aos dados exige a chave interna (`X-Internal-Api-Key`),
  que vive apenas no ambiente do servidor e no proxy do painel.

## 4. Segurança de aplicação

- **Superfícies**: `/v1/*` público (app), `/v1/internal/*` e `/v1/admin/*`
  exigem `X-Internal-Api-Key` (middleware em `main.py`); webhook do gateway
  exige token dedicado (header próprio ou Basic auth) e fica fechado se o
  token não estiver configurado.
- **Headers de segurança** em toda resposta: nosniff, X-Frame-Options DENY,
  Referrer-Policy no-referrer, HSTS (`main.py`).
- **Segredos**: 100% em variáveis de ambiente (Render); `.env` fora do git;
  nenhuma credencial no repositório.
- **SQL**: todas as queries usam bind parameters (SQLAlchemy `text()` com
  `:param`) — sem interpolação de entrada do usuário.
- **Dinheiro**: sempre `Decimal` com arredondamento explícito
  (`shared/dinheiro.py`), nunca float.

## 5. Escalabilidade — desenho atual e dívidas conscientes

Arquitetura por domínio (camadas `routes → service → repository`, uma pasta
por domínio — ver README). Decisões que sustentam escala:

- Índices em todas as consultas quentes (por conta, por vigência, por
  status; índice parcial para estoque de cupons livres).
- Locks de linha (`FOR UPDATE`, `SKIP LOCKED`) nos pontos de concorrência
  (lotes FIFO, webhook de compra, claim de cupom) — sem locks globais.
- I/O externo (gateway, SEFAZ) sempre **fora** de transação de banco.
- Consultas pagas (Infosimples) com throttle por registro (1 tentativa/5min)
  e pré-filtro gratuito por CNPJ embutido na chave da NFC-e.

Dívidas registradas, em ordem de prioridade (nenhuma bloqueia o volume
atual; todas têm o ponto de corte documentado):

1. **Autenticação por usuário nas rotas do app** (hoje valida `account_id`
   mas não exige sessão/token) — obrigatória antes de escala pública; junto,
   rate-limit na busca por CPF.
2. **CORS restrito ao domínio real do app** (hoje `*` para o Lovable).
3. **Fila de mensagens**: processamento assíncrono usa BackgroundTasks
   (in-process); os services já são independentes do framework — migrar para
   worker/fila é mover a chamada.
4. **Imagens em object storage** (hoje bytea no Postgres; o contrato é URL,
   trocar o destino não afeta frontends).
5. **Saldo por SUM** → materialized view/cache se virar gargalo (nunca saldo
   editável).
6. **Virada automática de série do sorteio** ao passar de 100.000 números.

## 6. Testes

Suíte com 205 testes (unit + integração com Postgres real), cobrindo:
idempotência de todos os fluxos de escrita, imutabilidade das tabelas de
auditoria (tentativas de UPDATE/DELETE falham), concorrência (claims
atômicos), regras de negócio do regulamento (exemplo-ouro da apuração) e
contratos de erro da API. Roda em CI local com `pytest` (ver README).
