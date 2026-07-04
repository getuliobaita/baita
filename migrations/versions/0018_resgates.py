"""resgates

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-04

Nao definida na spec original (secao 4.4 so da os contratos de API), mas
essencial pro fluxo nao-negociavel "debito_resgate so e gravado apos
confirmacao do fornecedor externo -- nunca antes": precisamos de algum
lugar pra guardar a RESERVA de coins entre o pedido ao fornecedor e a
confirmacao, sem tocar em ledger_events (append-only, so credito/debito
efetivo) nem em lotes_creditos/consumo_lotes (so consumidos na confirmacao).
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE resgates (
            resgate_id           UUID PRIMARY KEY,
            account_id           UUID NOT NULL REFERENCES wallet_accounts(account_id),
            catalogo_item_id     UUID NOT NULL REFERENCES catalogo_itens(item_id),
            coins_reservados     NUMERIC(14,2) NOT NULL CHECK (coins_reservados > 0),
            idempotency_key      VARCHAR(100) UNIQUE NOT NULL,
            status               VARCHAR(20) NOT NULL DEFAULT 'reservado',
            fornecedor           VARCHAR(50) NOT NULL,
            pedido_externo_id    VARCHAR(100),
            codigo_entrega       VARCHAR(100),
            instrucoes           TEXT,
            motivo_cancelamento  TEXT,
            event_id             UUID REFERENCES ledger_events(event_id),
            criado_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
            atualizado_em        TIMESTAMPTZ
        );

        CREATE INDEX ix_resgates_account_status ON resgates (account_id, status);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE resgates;")
