"""wallet_accounts.tags + indices de busca do admin de usuarios

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-05

Estrutura replicada do manager da Urbis (referencia do usuario): tags
livres por usuario (chips tipo "Tag_Sorteio_Beneficio_Prod") e busca por
nome/email na listagem administrativa.
"""
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE wallet_accounts
            ADD COLUMN tags JSONB NOT NULL DEFAULT '[]'::jsonb;

        CREATE INDEX ix_wallet_accounts_nome ON wallet_accounts (lower(nome));
        CREATE INDEX ix_wallet_accounts_email ON wallet_accounts (lower(email));
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX ix_wallet_accounts_nome;
        DROP INDEX ix_wallet_accounts_email;
        ALTER TABLE wallet_accounts DROP COLUMN tags;
        """
    )
