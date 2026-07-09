"""gestao de cadastros pelo painel: trilha de auditoria das alteracoes

Revision ID: 0040
Revises: 0039
Create Date: 2026-07-10

O manager passa a poder criar e editar cadastros (incluindo corrigir CPF).
Toda acao administrativa sobre um cadastro fica registrada de forma
imutavel em admin_usuarios_alteracoes: quem foi alterado, qual acao e
quais campos mudaram (valores novos) -- "para nao perdermos registro",
requisito explicito do usuario.
"""
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE admin_usuarios_alteracoes (
            alteracao_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id    UUID NOT NULL,
            acao          VARCHAR(20) NOT NULL CHECK (acao IN ('criar', 'editar')),
            campos        JSONB NOT NULL,
            criado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_admin_usuarios_alteracoes_account
            ON admin_usuarios_alteracoes (account_id, criado_em DESC);

        CREATE FUNCTION admin_alteracoes_forbid_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'admin_usuarios_alteracoes e um log imutavel: % nao e permitido', TG_OP;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_admin_alteracoes_immutable
            BEFORE UPDATE OR DELETE ON admin_usuarios_alteracoes
            FOR EACH ROW EXECUTE FUNCTION admin_alteracoes_forbid_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_admin_alteracoes_immutable ON admin_usuarios_alteracoes;
        DROP FUNCTION IF EXISTS admin_alteracoes_forbid_mutation();
        DROP TABLE admin_usuarios_alteracoes;
        """
    )
