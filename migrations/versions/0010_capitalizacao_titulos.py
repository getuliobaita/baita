"""capitalizacao_titulos

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-04
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE capitalizacao_titulos (
            titulo_id           UUID PRIMARY KEY,
            event_id            UUID NOT NULL UNIQUE REFERENCES ledger_events(event_id),
            numero_titulo_susep VARCHAR(50) NOT NULL,
            plano_id            VARCHAR(50) NOT NULL,
            valor_pago          NUMERIC(14,2) NOT NULL CHECK (valor_pago > 0),
            criado_em           TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE capitalizacao_titulos;")
