"""numeros_sorte_faixas

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-04
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE numeros_sorte_faixas (
            faixa_id         UUID PRIMARY KEY,
            account_id       UUID NOT NULL REFERENCES wallet_accounts(account_id),
            event_id         UUID NOT NULL UNIQUE REFERENCES ledger_events(event_id),
            sorteio_id       UUID NOT NULL REFERENCES sorteios(sorteio_id),
            numero_inicial   BIGINT NOT NULL,
            numero_final     BIGINT NOT NULL CHECK (numero_final >= numero_inicial),
            status           VARCHAR(20) NOT NULL DEFAULT 'ativo',
            criado_em        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- busca por intervalo: dado um numero sorteado, localizar a faixa que o contem
        CREATE INDEX ix_numeros_sorte_faixas_sorteio_intervalo
            ON numeros_sorte_faixas (sorteio_id, numero_inicial, numero_final);

        CREATE INDEX ix_numeros_sorte_faixas_account
            ON numeros_sorte_faixas (account_id, sorteio_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE numeros_sorte_faixas;")
