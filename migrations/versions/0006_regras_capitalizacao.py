"""regras_capitalizacao

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-04
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE regras_capitalizacao (
            regra_id         UUID PRIMARY KEY,
            nome_campanha    VARCHAR(100),
            vigencia_inicio  TIMESTAMPTZ NOT NULL,
            vigencia_fim     TIMESTAMPTZ,
            faixas           JSONB NOT NULL,
            status           VARCHAR(20) NOT NULL DEFAULT 'ativa',
            criado_em        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX ix_regras_capitalizacao_vigencia
            ON regras_capitalizacao (vigencia_inicio, vigencia_fim);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE regras_capitalizacao;")
