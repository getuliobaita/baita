"""wallet_accounts: dados de cadastro (nome, celular, nascimento, endereco)

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-05

Fluxo de compra pra quem nao e usuario: CPF -> busca -> se nao existe,
coleta nome, celular, data de nascimento e endereco (CEP via ViaCEP no
frontend + numero/complemento). Tudo nullable: contas antigas continuam
validas com cadastro incompleto ate o cliente completar.
"""
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE wallet_accounts
            ADD COLUMN nome VARCHAR(150),
            ADD COLUMN celular VARCHAR(11),
            ADD COLUMN data_nascimento DATE,
            ADD COLUMN cep VARCHAR(8),
            ADD COLUMN logradouro VARCHAR(200),
            ADD COLUMN numero VARCHAR(20),
            ADD COLUMN complemento VARCHAR(100),
            ADD COLUMN bairro VARCHAR(100),
            ADD COLUMN cidade VARCHAR(100),
            ADD COLUMN uf VARCHAR(2);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE wallet_accounts
            DROP COLUMN nome,
            DROP COLUMN celular,
            DROP COLUMN data_nascimento,
            DROP COLUMN cep,
            DROP COLUMN logradouro,
            DROP COLUMN numero,
            DROP COLUMN complemento,
            DROP COLUMN bairro,
            DROP COLUMN cidade,
            DROP COLUMN uf;
        """
    )
