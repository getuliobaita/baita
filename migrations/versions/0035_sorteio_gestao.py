"""gestao de sorteios: titulo/campanha, periodo, datas de apuracao e
divulgacao, tabela de premios

Revision ID: 0035
Revises: 0034
Create Date: 2026-07-07

O painel passa a gerenciar cada edicao do sorteio com os campos do
regulamento (Promocao Comercial): titulo da campanha, periodo de
participacao, data da apuracao (extracao da Loteria Federal), data de
divulgacao dos ganhadores e a tabela de premios. Os premios ficam no
proprio sorteio (fonte da verdade da edicao) e passam a alimentar a
apuracao por padrao.
"""
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

# Premios da edicao atual: 1x R$50.000 + 2x R$25.000.
# NB: espaco depois de cada ":" e proposital -- sem ele, o SQLAlchemy trata
# ":1"/":2" como bind params ao executar o DDL literal.
_PREMIOS_PADRAO = (
    '[{"valor": "50000.00", "quantidade": 1}, {"valor": "25000.00", "quantidade": 2}]'
)


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE sorteios ADD COLUMN titulo VARCHAR(120);
        ALTER TABLE sorteios ADD COLUMN periodo_inicio DATE;
        ALTER TABLE sorteios ADD COLUMN periodo_fim DATE;
        ALTER TABLE sorteios ADD COLUMN data_apuracao DATE;
        ALTER TABLE sorteios ADD COLUMN data_divulgacao DATE;
        ALTER TABLE sorteios ADD COLUMN premios JSONB NOT NULL
            DEFAULT '{_PREMIOS_PADRAO}'::jsonb;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE sorteios DROP COLUMN premios;
        ALTER TABLE sorteios DROP COLUMN data_divulgacao;
        ALTER TABLE sorteios DROP COLUMN data_apuracao;
        ALTER TABLE sorteios DROP COLUMN periodo_fim;
        ALTER TABLE sorteios DROP COLUMN periodo_inicio;
        ALTER TABLE sorteios DROP COLUMN titulo;
        """
    )
