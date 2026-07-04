"""consumo_lotes

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-04
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE consumo_lotes (
            consumo_id       UUID PRIMARY KEY,
            debito_event_id  UUID NOT NULL REFERENCES ledger_events(event_id),
            lote_id          UUID NOT NULL REFERENCES lotes_creditos(lote_id),
            coins_consumidos NUMERIC(14,2) NOT NULL CHECK (coins_consumidos > 0)
        );

        CREATE INDEX ix_consumo_lotes_debito_event_id ON consumo_lotes (debito_event_id);
        CREATE INDEX ix_consumo_lotes_lote_id ON consumo_lotes (lote_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE consumo_lotes;")
