"""campanhas_multiplicador

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-04

Nota: escopo_parceiro fica sem FK por enquanto -- a tabela `parceiros` so
existe a partir da Fase 3 (pipeline de nota fiscal). A FK sera adicionada
via ALTER TABLE quando `parceiros` for criada. Ate la, escopo_parceiro
sempre sera NULL (campanha geral de capitalizacao), que e o unico caso que
a Fase 2 usa.
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE campanhas_multiplicador (
            campanha_id      UUID PRIMARY KEY,
            nome             VARCHAR(100) NOT NULL,
            multiplicador    NUMERIC(4,2) NOT NULL CHECK (multiplicador > 0),
            vigencia_inicio  TIMESTAMPTZ NOT NULL,
            vigencia_fim     TIMESTAMPTZ NOT NULL,
            prioridade       INT NOT NULL DEFAULT 0,
            escopo_parceiro  UUID,
            status           VARCHAR(20) NOT NULL DEFAULT 'ativa',
            criado_em        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX ix_campanhas_multiplicador_vigencia
            ON campanhas_multiplicador (vigencia_inicio, vigencia_fim, escopo_parceiro);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE campanhas_multiplicador;")
