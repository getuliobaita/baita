"""assinaturas: cartao de credito com recorrencia (Pagar.me Subscriptions)

Revision ID: 0039
Revises: 0038
Create Date: 2026-07-08

Assinatura mensal do clube no cartao. O cartao NUNCA passa pelo nosso
backend (PCI): o app tokeniza direto na Pagar.me (chave publica) e manda
so o card_token; aqui criamos a assinatura (secret key) e guardamos apenas
a referencia (gateway_subscription_id) + bandeira/final do cartao pra
exibicao.

Cada ciclo pago (webhook invoice.paid) vira uma compra_capitalizacao
confirmada pelo fluxo normal -- coins, numeros da sorte, titulo e NFS-e
identicos a uma compra avulsa, com idempotencia por invoice.
"""
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE assinaturas (
            assinatura_id            UUID PRIMARY KEY,
            account_id               UUID NOT NULL REFERENCES wallet_accounts(account_id),
            quantidade_pacotes       INTEGER NOT NULL CHECK (quantidade_pacotes BETWEEN 1 AND 99),
            valor_reais              NUMERIC(14,2) NOT NULL,
            gateway                  VARCHAR(20) NOT NULL DEFAULT 'pagarme',
            gateway_subscription_id  VARCHAR(80) UNIQUE,
            status                   VARCHAR(30) NOT NULL DEFAULT 'aguardando_pagamento'
                CHECK (status IN ('aguardando_pagamento', 'ativa', 'inadimplente', 'cancelada')),
            cartao_bandeira          VARCHAR(30),
            cartao_ultimos4          VARCHAR(4),
            idempotency_key          VARCHAR(100) UNIQUE NOT NULL,
            criado_em                TIMESTAMPTZ NOT NULL DEFAULT now(),
            atualizado_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
            cancelada_em             TIMESTAMPTZ
        );

        CREATE INDEX ix_assinaturas_account ON assinaturas (account_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE assinaturas;")
