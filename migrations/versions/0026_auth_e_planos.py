"""auth (email + senha) e planos de compra

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-05

Replica o formato do site atual: login por "Email ou CPF" + senha, e senha
temporaria enviada por WhatsApp quando o cadastro nao define uma. A tabela
planos alimenta a tela de planos de compra (presets de pacotes de R$20 --
a compra continua aceitando qualquer quantidade de 1 a 99, o plano e so
uma sugestao de vitrine).
"""
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE wallet_accounts
            ADD COLUMN email VARCHAR(150) UNIQUE,
            ADD COLUMN senha_hash VARCHAR(300);

        CREATE TABLE planos (
            plano_id           UUID PRIMARY KEY,
            nome               VARCHAR(100) NOT NULL,
            quantidade_pacotes INT NOT NULL CHECK (quantidade_pacotes BETWEEN 1 AND 99),
            descricao          VARCHAR(200),
            destaque           BOOLEAN NOT NULL DEFAULT false,
            ordem              INT NOT NULL DEFAULT 0,
            status             VARCHAR(20) NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'inativo')),
            criado_em          TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        INSERT INTO planos (plano_id, nome, quantidade_pacotes, descricao, destaque, ordem) VALUES
            (gen_random_uuid(), 'Baita',        1,  'R$20 -- teu clube por um mes e tu ja concorre',            false, 1),
            (gen_random_uuid(), 'Baita Triplo', 3,  'R$60 -- 3x mais coins e 3x mais numeros da sorte',         true,  2),
            (gen_random_uuid(), 'Baita Semestre', 6, 'R$120 -- 6 pacotes de uma vez',                           false, 3),
            (gen_random_uuid(), 'Baita do Ano', 12, 'R$240 -- 12 pacotes, o ano todo aproveitando',             false, 4);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE planos;
        ALTER TABLE wallet_accounts DROP COLUMN email, DROP COLUMN senha_hash;
        """
    )
