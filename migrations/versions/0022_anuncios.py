"""anuncios (banners/midia gerenciados pelo painel admin)

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-05

Feature nova a pedido do usuario: espacos de anuncio no app do cliente
(banner na home, card patrocinado no grid de beneficios, banner de rodape)
gerenciaveis pelo painel administrativo sem redeploy do frontend.
"""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE anuncios (
            anuncio_id       UUID PRIMARY KEY,
            titulo           VARCHAR(150) NOT NULL,
            slot             VARCHAR(30) NOT NULL
                CHECK (slot IN ('banner_home', 'card_patrocinado', 'banner_rodape')),
            imagem_url       VARCHAR(500) NOT NULL,
            link_destino     VARCHAR(500),
            prioridade       INT NOT NULL DEFAULT 0,
            vigencia_inicio  TIMESTAMPTZ,
            vigencia_fim     TIMESTAMPTZ,
            status           VARCHAR(20) NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'inativo')),
            criado_em        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX ix_anuncios_slot_status ON anuncios (slot, status, prioridade DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE anuncios;")
