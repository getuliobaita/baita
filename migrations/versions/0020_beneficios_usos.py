"""beneficios_usos

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-04

Regra de negocio confirmada com o usuario: 1 Baita Coin = 1 uso pontual de
QUALQUER beneficio (desconto ou cashback) -- cada uso debita exatamente
1.00 coin e gera um cupom/link novo na hora, sem limite de repeticao por
parceiro (so limitado pelo saldo).
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE beneficios_usos (
            uso_id           UUID PRIMARY KEY,
            account_id       UUID NOT NULL REFERENCES wallet_accounts(account_id),
            beneficio_id     UUID NOT NULL REFERENCES beneficios(beneficio_id),
            event_id         UUID NOT NULL REFERENCES ledger_events(event_id),
            idempotency_key  VARCHAR(100) UNIQUE NOT NULL,
            codigo_cupom     VARCHAR(100),
            link_afiliado    VARCHAR(300),
            criado_em        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX ix_beneficios_usos_account ON beneficios_usos (account_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE beneficios_usos;")
