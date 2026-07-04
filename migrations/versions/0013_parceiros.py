"""parceiros

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-04
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE parceiros (
            parceiro_id      UUID PRIMARY KEY,
            cnpj             VARCHAR(14) UNIQUE NOT NULL,
            nome_fantasia    VARCHAR(150),
            status           VARCHAR(20) NOT NULL DEFAULT 'ativo',
            canal_nf         BOOLEAN NOT NULL DEFAULT true,
            canal_api        BOOLEAN NOT NULL DEFAULT false,
            criado_em        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- Promessa da migration 0007: agora que parceiros existe, a FK que
        -- faltava em campanhas_multiplicador.escopo_parceiro pode ser criada.
        ALTER TABLE campanhas_multiplicador
            ADD CONSTRAINT fk_campanhas_multiplicador_escopo_parceiro
            FOREIGN KEY (escopo_parceiro) REFERENCES parceiros(parceiro_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE campanhas_multiplicador DROP CONSTRAINT fk_campanhas_multiplicador_escopo_parceiro;
        DROP TABLE parceiros;
        """
    )
