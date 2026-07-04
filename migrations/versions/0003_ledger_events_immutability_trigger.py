"""ledger_events immutability trigger

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-04

Regra nao-negociavel da spec: "Nenhum UPDATE, nenhum DELETE em ledger_events".
Isso e reforcado aqui no proprio banco (defesa em profundidade), nao apenas
por disciplina de codigo na aplicacao -- qualquer tentativa de UPDATE ou
DELETE na tabela falha com excecao do Postgres, independente de quem/o que
esteja executando o SQL.
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION ledger_events_forbid_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'ledger_events e append-only: % nao e permitido (event_id=%). Use um evento de estorno.',
                TG_OP,
                OLD.event_id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_ledger_events_forbid_mutation
            BEFORE UPDATE OR DELETE ON ledger_events
            FOR EACH ROW
            EXECUTE FUNCTION ledger_events_forbid_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_ledger_events_forbid_mutation ON ledger_events;
        DROP FUNCTION IF EXISTS ledger_events_forbid_mutation();
        """
    )
