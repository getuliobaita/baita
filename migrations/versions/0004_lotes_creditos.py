"""lotes_creditos

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-04
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE lotes_creditos (
            lote_id          UUID PRIMARY KEY,
            event_id         UUID NOT NULL REFERENCES ledger_events(event_id),
            account_id       UUID NOT NULL REFERENCES wallet_accounts(account_id),
            coins_originais  NUMERIC(14,2) NOT NULL CHECK (coins_originais > 0),
            coins_consumidos NUMERIC(14,2) NOT NULL DEFAULT 0
                CHECK (coins_consumidos >= 0 AND coins_consumidos <= coins_originais),
            data_credito     TIMESTAMPTZ NOT NULL,
            data_expiracao   TIMESTAMPTZ NOT NULL,
            status           VARCHAR(20) NOT NULL DEFAULT 'ativo'
        );

        -- consumo FIFO: lotes ativos de uma conta, do mais antigo pro mais novo
        CREATE INDEX ix_lotes_creditos_conta_status_credito
            ON lotes_creditos (account_id, status, data_credito);

        -- job diario de expiracao: varre todos os lotes ativos vencidos
        CREATE INDEX ix_lotes_creditos_status_expiracao
            ON lotes_creditos (status, data_expiracao);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE lotes_creditos;")
