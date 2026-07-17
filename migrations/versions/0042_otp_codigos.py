"""otp_codigos: login por codigo (SMS/WhatsApp), sem depender de senha

Revision ID: 0042
Revises: 0041
Create Date: 2026-07-17

Codigo de uso unico enviado pro celular cadastrado da conta. Resolve tanto
"esqueci minha senha" (entra sem senha) quanto o login passwordless.

Seguranca:
- codigo guardado HASHEADO (pbkdf2), nunca em texto puro
- expira em poucos minutos; maximo de tentativas por codigo
- rate limit por conta (contagem de codigos recentes) contra flood de SMS
- codigo so vai pro celular JA CADASTRADO na conta -- o numero nao vem do
  request, entao um atacante nao redireciona o codigo pra outro aparelho
"""
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE otp_codigos (
            otp_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id   UUID NOT NULL REFERENCES wallet_accounts(account_id),
            codigo_hash  TEXT NOT NULL,
            canal        VARCHAR(20) NOT NULL DEFAULT 'whatsapp',
            expira_em    TIMESTAMPTZ NOT NULL,
            tentativas   INTEGER NOT NULL DEFAULT 0,
            usado_em     TIMESTAMPTZ,
            criado_em    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_otp_account_recentes ON otp_codigos (account_id, criado_em DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE otp_codigos;")
