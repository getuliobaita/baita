"""beneficios: modos de resgate flexiveis + pagina de detalhe do parceiro

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-08

Os parceiros reais tem formas de resgate diferentes; o beneficio ganha um
`modo_resgate` que define o que o cliente recebe ao usar:

- 'automatico'    comportamento legado (adapter: desconto->cupom mock,
                  cashback->link mock)
- 'cupom_unico'   o MESMO codigo pra todos (resgate_config.codigo)
- 'cupom_por_cpf' codigo INDIVIDUAL por uso, consumido de um estoque
                  importado pelo painel (tabela beneficios_cupons)
- 'cpf_no_caixa'  sem codigo: o cliente se identifica pelo CPF no caixa
                  (so instrucoes_resgate)
- 'link'          redireciona pro link do parceiro (resgate_config.url)

`resgate_config` e JSONB livre pra parametros do modo -- modos novos entram
sem migration. `descricao_completa` e `instrucoes_resgate` alimentam a
pagina de detalhe do parceiro no app.

`beneficios_usos.event_id` passa a aceitar NULL: beneficio com custo 0
(ex: desconto no caixa cortesia) nao gera debito no ledger (que proibe
eventos de 0 coins), mas o uso continua registrado.
"""
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE beneficios ADD COLUMN modo_resgate VARCHAR(30) NOT NULL DEFAULT 'automatico'
            CHECK (modo_resgate IN ('automatico', 'cupom_unico', 'cupom_por_cpf', 'cpf_no_caixa', 'link'));
        ALTER TABLE beneficios ADD COLUMN resgate_config JSONB NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE beneficios ADD COLUMN descricao_completa TEXT;
        ALTER TABLE beneficios ADD COLUMN instrucoes_resgate TEXT;

        ALTER TABLE beneficios_usos ALTER COLUMN event_id DROP NOT NULL;

        -- custo zero passa a ser valido (ex: desconto no caixa cortesia);
        -- a regra antiga exigia > 0
        ALTER TABLE beneficios DROP CONSTRAINT beneficios_custo_em_coins_check;
        ALTER TABLE beneficios ADD CONSTRAINT beneficios_custo_em_coins_check
            CHECK (custo_em_coins >= 0);

        CREATE TABLE beneficios_cupons (
            cupom_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            beneficio_id  UUID NOT NULL REFERENCES beneficios(beneficio_id),
            codigo        VARCHAR(100) NOT NULL,
            account_id    UUID REFERENCES wallet_accounts(account_id),
            atribuido_em  TIMESTAMPTZ,
            criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (beneficio_id, codigo)
        );

        CREATE INDEX ix_beneficios_cupons_disponiveis
            ON beneficios_cupons (beneficio_id) WHERE account_id IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE beneficios_cupons;
        ALTER TABLE beneficios DROP CONSTRAINT beneficios_custo_em_coins_check;
        ALTER TABLE beneficios ADD CONSTRAINT beneficios_custo_em_coins_check
            CHECK (custo_em_coins > 0);
        ALTER TABLE beneficios_usos ALTER COLUMN event_id SET NOT NULL;
        ALTER TABLE beneficios DROP COLUMN instrucoes_resgate;
        ALTER TABLE beneficios DROP COLUMN descricao_completa;
        ALTER TABLE beneficios DROP COLUMN resgate_config;
        ALTER TABLE beneficios DROP COLUMN modo_resgate;
        """
    )
