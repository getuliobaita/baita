"""beneficios.custo_em_coins (custo configuravel por parceiro)

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-04

Substitui a regra fixa global de "1 coin = 1 uso" por um custo
configuravel POR BENEFICIO -- decisao do usuario pra permitir ajustar a
mecanica de pontos por parceiro (ex: um parceiro premium pode custar mais
que 1 coin). Os 140 beneficios ja cadastrados ficam em 1.00 por padrao,
preservando o comportamento atual ate alguem ajustar via admin.
"""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE beneficios
            ADD COLUMN custo_em_coins NUMERIC(14,2) NOT NULL DEFAULT 1.00 CHECK (custo_em_coins > 0);
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE beneficios DROP COLUMN custo_em_coins;")
