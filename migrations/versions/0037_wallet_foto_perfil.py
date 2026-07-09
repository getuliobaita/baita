"""wallet_accounts: foto de perfil (url da imagem)

Revision ID: 0037
Revises: 0036
Create Date: 2026-07-07

A foto de perfil precisa persistir no servidor -- guardada so no navegador,
ela se perde a cada novo login. A imagem e enviada pelo mesmo armazenamento
das imagens (servido em /v1/anuncios/imagens/{id}); aqui guardamos a URL na
propria conta e a devolvemos no login/consulta.
"""
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE wallet_accounts ADD COLUMN foto_url TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE wallet_accounts DROP COLUMN foto_url;")
