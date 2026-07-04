"""regras_parceiro

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-04
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE regras_parceiro (
            regra_id             UUID PRIMARY KEY,
            parceiro_cnpj        VARCHAR(14) NOT NULL REFERENCES parceiros(cnpj),
            vigencia_inicio      TIMESTAMPTZ NOT NULL,
            vigencia_fim         TIMESTAMPTZ,
            percentual_cashback  NUMERIC(5,2) NOT NULL CHECK (percentual_cashback > 0),
            teto_por_nota        NUMERIC(14,2) CHECK (teto_por_nota > 0),
            teto_por_cliente_mes NUMERIC(14,2) CHECK (teto_por_cliente_mes > 0),
            status               VARCHAR(20) NOT NULL DEFAULT 'ativa',
            criado_em            TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX ix_regras_parceiro_vigencia
            ON regras_parceiro (parceiro_cnpj, vigencia_inicio, vigencia_fim);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE regras_parceiro;")
