"""anuncios_imagens (upload de banners direto no backend)

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-05

Armazena a imagem em BYTEA no proprio Postgres em vez de exigir hospedagem
externa -- adequado pra escala atual (banners de poucas centenas de KB,
poucas dezenas de anuncios). Se um dia virar gargalo, migra pra um object
storage (S3 e afins) sem mudar o contrato da API: o GET publico continua
sendo a URL da imagem.
"""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE anuncios_imagens (
            imagem_id     UUID PRIMARY KEY,
            content_type  VARCHAR(50) NOT NULL,
            dados         BYTEA NOT NULL,
            tamanho_bytes INT NOT NULL,
            criado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE anuncios_imagens;")
