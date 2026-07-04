"""seed: regra de capitalizacao padrao (1 coin = 1 real) + primeiro sorteio aberto

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-04

Decisao de negocio confirmada com o usuario (nao vem da spec original, que
trazia faixas progressivas como exemplo): a regra e sempre 1 coin por real,
faixa unica. vigencia_inicio fixa no passado pra garantir que a regra ja
esteja vigente em qualquer ambiente onde a migration rodar.
"""
import uuid

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_REGRA_ID = str(uuid.uuid4())
_SORTEIO_ID = str(uuid.uuid4())


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO regras_capitalizacao (regra_id, nome_campanha, vigencia_inicio, vigencia_fim, faixas, status)
        VALUES (
            '{_REGRA_ID}',
            'Regra padrao -- 1 coin por real',
            '2020-01-01T00:00:00Z',
            NULL,
            '[{{"valor_min": 0, "valor_max": null, "coins_por_real": 1.0}}]'::jsonb,
            'ativa'
        );

        INSERT INTO sorteios (sorteio_id, data_sorteio, status)
        VALUES ('{_SORTEIO_ID}', now() + INTERVAL '90 days', 'aberto');
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DELETE FROM regras_capitalizacao WHERE regra_id = '{_REGRA_ID}';
        DELETE FROM sorteios WHERE sorteio_id = '{_SORTEIO_ID}';
        """
    )
