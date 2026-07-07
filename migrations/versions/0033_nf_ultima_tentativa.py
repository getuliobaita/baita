"""nf_submissoes: controle de retentativa de consulta a SEFAZ

Cada consulta ao provedor (Infosimples) e PAGA. Sem controle, todo GET de
status de uma nota 'recebida' dispara nova consulta -- com o app fazendo
polling a cada 3s, uma nota travada viraria dezenas de consultas cobradas.
ultima_tentativa_em permite reconsultar no maximo 1x por intervalo
(configuravel, padrao 5 min) e tambem serve de claim atomico contra
consultas concorrentes duplicadas.
"""
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE nf_submissoes ADD COLUMN ultima_tentativa_em timestamptz;")


def downgrade() -> None:
    op.execute("ALTER TABLE nf_submissoes DROP COLUMN ultima_tentativa_em;")
