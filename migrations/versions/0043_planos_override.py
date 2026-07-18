"""planos: override de coins e numeros da sorte por plano + vinculo compra->plano

Revision ID: 0043
Revises: 0042
Create Date: 2026-07-17

Permite ao painel definir, por plano:
- coins_override: total EXATO de coins que o plano credita (ignora a taxa
  global). Alavanca de campanha. NULL = deriva do valor x taxa vigente.
- numeros_sorte_override: numeros da sorte fixos por plano. NULL = deriva.
  ATENCAO: cada numero e um titulo de capitalizacao (SUSEP, R$20 = 1
  titulo). O override so tem efeito com PLANOS_NUMEROS_OVERRIDE_HABILITADO
  no ambiente -- trava proposital ate a VIACAP autorizar o desacoplamento.

E amarra a compra ao plano (plano_id) pra que o override valha no CREDITO
real, nao so na vitrine. Compra avulsa (sem plano) continua com plano_id
NULL e a derivacao padrao.
"""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE planos ADD COLUMN coins_override NUMERIC(14,2)
            CHECK (coins_override IS NULL OR coins_override > 0);
        ALTER TABLE planos ADD COLUMN numeros_sorte_override INTEGER
            CHECK (numeros_sorte_override IS NULL OR numeros_sorte_override >= 0);
        ALTER TABLE compras_capitalizacao ADD COLUMN plano_id UUID;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE compras_capitalizacao DROP COLUMN plano_id;
        ALTER TABLE planos DROP COLUMN numeros_sorte_override;
        ALTER TABLE planos DROP COLUMN coins_override;
        """
    )
