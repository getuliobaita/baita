"""nf_submissoes

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-04

Dois desvios deliberados da spec, ambos necessarios pro pipeline descrito
na propria spec fazer sentido de ponta a ponta:

1. `chave_acesso` fica NULLABLE (spec original: UNIQUE NOT NULL). O fallback
   de OCR explicitamente permite que uma submissao va pra `revisao_manual`
   SEM nunca ter conseguido extrair a chave de acesso -- exigir NOT NULL
   tornaria esse caminho impossivel de persistir.
2. Adicionamos `idempotency_key` (UNIQUE NOT NULL) e `event_id` (FK pra
   ledger_events). O primeiro cobre a convencao geral da spec ("todo
   endpoint que gera efeito no ledger exige Idempotency-Key") pro caso de
   retry de rede na propria chamada de submissao -- distinto da dedup por
   chave_acesso, que protege contra a MESMA nota fiscal fisica sendo
   submetida duas vezes. O segundo linka a submissao ao credito efetivo,
   no mesmo padrao usado em compras_capitalizacao.
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE nf_submissoes (
            submissao_id     UUID PRIMARY KEY,
            account_id       UUID NOT NULL REFERENCES wallet_accounts(account_id),
            idempotency_key  VARCHAR(100) UNIQUE NOT NULL,
            chave_acesso     VARCHAR(44) UNIQUE,
            uf               VARCHAR(2),
            cnpj_emitente    VARCHAR(14),
            valor_total      NUMERIC(14,2),
            status           VARCHAR(20) NOT NULL,
            motivo_rejeicao  TEXT,
            event_id         UUID REFERENCES ledger_events(event_id),
            criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
            processado_em    TIMESTAMPTZ
        );

        CREATE INDEX ix_nf_submissoes_account ON nf_submissoes (account_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE nf_submissoes;")
