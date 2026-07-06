"""anuncios: slot livre (sem CHECK de lista fixa)

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-06

Novos espacos de banner/pop-up passam a ser criados sem deploy: o painel
cadastra o anuncio com um slot novo (ex: 'popup_home', 'banner_beneficios')
e o app renderiza um AdSlot com o mesmo nome -- backend vira so o
armazenamento/filtro, sem lista fixa.
"""
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE anuncios DROP CONSTRAINT anuncios_slot_check;")


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE anuncios ADD CONSTRAINT anuncios_slot_check
            CHECK (slot IN ('banner_home', 'card_patrocinado', 'banner_rodape'));
        """
    )
