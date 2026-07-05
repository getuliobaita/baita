"""planos: metodos de pagamento, periodicidade e vantagens

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-05

Modelo de venda estilo clube de assinatura (referencia do usuario:
Familhao): cada plano define quais metodos de pagamento aceita (pix
avulso, pix recorrente, cartao de credito com recorrencia), se e compra
unica ou assinatura mensal, e a lista de vantagens exibida no card
("o que tu ganha"). A cobranca recorrente em si e responsabilidade do
gateway (mockado) -- aqui fica a configuracao comercial.
"""
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE planos
            ADD COLUMN metodos_pagamento JSONB NOT NULL DEFAULT '["pix"]'::jsonb,
            ADD COLUMN periodicidade VARCHAR(20) NOT NULL DEFAULT 'unica'
                CHECK (periodicidade IN ('unica', 'mensal')),
            ADD COLUMN vantagens JSONB NOT NULL DEFAULT '[]'::jsonb;

        -- Planos seed ganham a configuracao padrao do clube: o mensal
        -- (1 pacote) vira assinatura com todos os metodos; os maiores
        -- ficam como compra unica pix/cartao.
        UPDATE planos SET
            metodos_pagamento = '["pix", "pix_recorrente", "cartao_credito_recorrente"]'::jsonb,
            periodicidade = 'mensal',
            vantagens = '["20 Baita Coins todo mes", "1 numero da sorte por mes", "Descontos e cashback em 140+ parceiros"]'::jsonb
        WHERE quantidade_pacotes = 1;

        UPDATE planos SET
            metodos_pagamento = '["pix", "cartao_credito_recorrente"]'::jsonb,
            vantagens = '["Coins na hora", "Mais numeros da sorte", "Descontos e cashback em 140+ parceiros"]'::jsonb
        WHERE quantidade_pacotes > 1;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE planos
            DROP COLUMN metodos_pagamento,
            DROP COLUMN periodicidade,
            DROP COLUMN vantagens;
        """
    )
