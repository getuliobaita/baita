"""beneficios: logo_url, imagem_capa_url e chamada

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-05

Vitrine de beneficios estilo clube de vantagens (referencia do usuario:
Livelo): a logo do parceiro vira o heroi do card, com uma imagem de capa
opcional e uma "chamada" -- copy curta de marketing gerenciada pelo painel
("Tenis novo com 8% de volta"), separada da descricao_oferta tecnica
("Ate 6% de Cashback"). Tudo opcional pra nao quebrar os 140 beneficios
ja cadastrados.
"""
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE beneficios
            ADD COLUMN logo_url VARCHAR(500),
            ADD COLUMN imagem_capa_url VARCHAR(500),
            ADD COLUMN chamada VARCHAR(150);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE beneficios
            DROP COLUMN logo_url,
            DROP COLUMN imagem_capa_url,
            DROP COLUMN chamada;
        """
    )
