"""wallet_accounts: consentimento de comunicacoes (e-mail em massa e push)

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-11

Base legal pro envio em massa (LGPD): cada conta guarda o consentimento e
QUANDO ele mudou pela ultima vez.

- aceita_comunicacoes_email: default TRUE (soft opt-in: comunicacoes do
  clube que o proprio cliente assinou), com opt-out facil pelo app.
- aceita_comunicacoes_push: default FALSE -- push SEMPRE exige acao
  explicita (o proprio navegador ja impoe a permissao; aqui registramos
  a escolha pra segmentacao e auditoria).
"""
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE wallet_accounts ADD COLUMN aceita_comunicacoes_email BOOLEAN NOT NULL DEFAULT true;
        ALTER TABLE wallet_accounts ADD COLUMN aceita_comunicacoes_push BOOLEAN NOT NULL DEFAULT false;
        ALTER TABLE wallet_accounts ADD COLUMN comunicacoes_atualizado_em TIMESTAMPTZ;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE wallet_accounts DROP COLUMN comunicacoes_atualizado_em;
        ALTER TABLE wallet_accounts DROP COLUMN aceita_comunicacoes_push;
        ALTER TABLE wallet_accounts DROP COLUMN aceita_comunicacoes_email;
        """
    )
