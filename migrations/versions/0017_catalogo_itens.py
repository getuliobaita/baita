"""catalogo_itens

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-04

Nao definida na spec original -- os contratos de resgate referenciam
`catalogo_item_id` mas nenhuma tabela de catalogo foi especificada. Modelo
minimo: 1 fornecedor fixo por item (o suficiente pra rotear pro
ProviderAdapter certo quando houver mais de um).
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE catalogo_itens (
            item_id      UUID PRIMARY KEY,
            nome         VARCHAR(150) NOT NULL,
            custo_coins  NUMERIC(14,2) NOT NULL CHECK (custo_coins > 0),
            fornecedor   VARCHAR(50) NOT NULL,
            status       VARCHAR(20) NOT NULL DEFAULT 'ativo',
            criado_em    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE catalogo_itens;")
