"""wallet_accounts

Revision ID: 0001
Revises:
Create Date: 2026-07-04
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE wallet_accounts (
            account_id       UUID PRIMARY KEY,
            cpf              VARCHAR(11) UNIQUE NOT NULL,
            status           VARCHAR(20) NOT NULL,
            criado_em        TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE wallet_accounts;")
