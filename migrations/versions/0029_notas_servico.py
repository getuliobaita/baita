"""notas_servico (NFS-e emitidas para as vendas do clube)

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-05

Emissao de nota fiscal de servico da VENDA do clube (via NFe.io) --
diferente de nf_submissoes (Fase 3), que LE notas de parceiros pro
cashback. Uma nota por compra confirmada; status rastreado pra permitir
reemissao em caso de falha (a emissao e best-effort apos o credito,
nunca bloqueia a confirmacao da compra).
"""
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE notas_servico (
            nota_id              UUID PRIMARY KEY,
            compra_id            UUID NOT NULL UNIQUE REFERENCES compras_capitalizacao(compra_id),
            account_id           UUID NOT NULL REFERENCES wallet_accounts(account_id),
            provider             VARCHAR(20) NOT NULL,
            provider_invoice_id  VARCHAR(100),
            valor_reais          NUMERIC(14,2) NOT NULL,
            status               VARCHAR(20) NOT NULL DEFAULT 'pendente'
                CHECK (status IN ('pendente', 'enviada', 'erro')),
            detalhe_erro         TEXT,
            criado_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
            atualizado_em        TIMESTAMPTZ
        );

        CREATE INDEX ix_notas_servico_status ON notas_servico (status);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE notas_servico;")
