"""sorteios

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-04

Tabela minima, nao definida na spec original -- necessaria pra saber a qual
sorteio atribuir novas faixas de numero_sorte. `proximo_numero_disponivel`
e o contador atomico global do sorteio (a spec pede numeracao "sequencial e
global por sorteio_id, gerada de forma atomica"; aqui isso e um UPDATE ...
RETURNING sob lock de linha, sem precisar de uma sequence por sorteio).
A gestao completa do ciclo de vida de um sorteio (execucao do sorteio em
si, contemplacao) fica fora do escopo da Fase 2.
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE sorteios (
            sorteio_id                UUID PRIMARY KEY,
            data_sorteio              TIMESTAMPTZ NOT NULL,
            status                    VARCHAR(20) NOT NULL DEFAULT 'aberto',
            proximo_numero_disponivel BIGINT NOT NULL DEFAULT 1 CHECK (proximo_numero_disponivel >= 1),
            criado_em                 TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX ix_sorteios_status ON sorteios (status);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE sorteios;")
