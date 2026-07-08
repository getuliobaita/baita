"""sorteio: banner da campanha (url da imagem)

Revision ID: 0036
Revises: 0035
Create Date: 2026-07-07

Cada edicao do sorteio ganha um banner (imagem da campanha) exibido no app.
A imagem e enviada pelo mesmo upload dos anuncios (POST /v1/admin/anuncios/
imagens, que devolve uma URL publica); aqui guardamos so a URL.
"""
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sorteios ADD COLUMN banner_url TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE sorteios DROP COLUMN banner_url;")
