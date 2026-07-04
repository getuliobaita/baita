"""compras_capitalizacao

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-04

Tabela nao definida na spec original -- necessaria pra rastrear o estado do
fluxo assincrono descrito em POST /v1/capitalizacao/compras (202, depois
confirmado via webhook). valor_reais = quantidade_pacotes * 20 e reforcado
tanto na aplicacao quanto no CHECK abaixo (pacotes fixos de R$20, ate 99).
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE compras_capitalizacao (
            compra_id              UUID PRIMARY KEY,
            account_id             UUID NOT NULL REFERENCES wallet_accounts(account_id),
            quantidade_pacotes     INT NOT NULL CHECK (quantidade_pacotes BETWEEN 1 AND 99),
            valor_reais            NUMERIC(14,2) NOT NULL CHECK (valor_reais = quantidade_pacotes * 20),
            idempotency_key        VARCHAR(100) UNIQUE NOT NULL,
            status                 VARCHAR(40) NOT NULL DEFAULT 'aguardando_confirmacao_pagamento',
            gateway                VARCHAR(30),
            gateway_transaction_id VARCHAR(100),
            event_id               UUID REFERENCES ledger_events(event_id),
            motivo_rejeicao        TEXT,
            criado_em              TIMESTAMPTZ NOT NULL DEFAULT now(),
            atualizado_em          TIMESTAMPTZ
        );

        CREATE INDEX ix_compras_capitalizacao_account ON compras_capitalizacao (account_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE compras_capitalizacao;")
