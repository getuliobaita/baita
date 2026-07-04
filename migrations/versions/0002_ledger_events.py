"""ledger_events

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-04

Nota de implementacao: a spec descreve as colunas de data como TIMESTAMP
(sem timezone). Aqui usamos TIMESTAMPTZ em todas as tabelas do ledger para
evitar bugs de fuso horario -- e o unico desvio deliberado da letra do
documento, sinalizado ao usuario antes da implementacao.
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ledger_events (
            event_id         UUID PRIMARY KEY,
            account_id       UUID NOT NULL REFERENCES wallet_accounts(account_id),
            tipo_evento      VARCHAR(30) NOT NULL,
            coins            NUMERIC(14,2) NOT NULL CHECK (coins <> 0),
            valor_reais      NUMERIC(14,2),
            referencia_id    UUID,
            idempotency_key  VARCHAR(100) UNIQUE NOT NULL,
            criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata         JSONB
        );

        CREATE INDEX ix_ledger_events_account_id ON ledger_events (account_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE ledger_events;")
