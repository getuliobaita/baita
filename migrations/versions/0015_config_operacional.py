"""config_operacional + seed (janela de aceite NF e limite antifraude diario)

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-04

Limite antifraude: a spec deixa em aberto ("Pendente -- conservador no
inicio, calibrar com dados reais depois") e sugere valores de exemplo
(R$500/dia, R$2.000/mes por parceiro). Uso o valor diario global sugerido
como seed -- ajustavel depois sem migration, e essa e a razao de existir
como linha de config_operacional em vez de constante no codigo.
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE config_operacional (
            chave  VARCHAR(50) PRIMARY KEY,
            valor  JSONB NOT NULL
        );

        INSERT INTO config_operacional (chave, valor) VALUES
            ('janela_aceite_nf', '{"horas_aceite_real": 48, "horas_comunicado_cliente": 24}'::jsonb),
            ('limite_antifraude_nf', '{"valor_maximo_por_cpf_dia": 500.00}'::jsonb);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE config_operacional;")
