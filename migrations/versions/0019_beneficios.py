"""beneficios (catalogo de descontos/cashback em formato de afiliados)

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-04

Feature nova, fora da spec original: catalogo de beneficios de terceiros
(desconto via cupom ou cashback via link de afiliado rastreado), separado
da tabela `parceiros` da Fase 3 -- aquela exige CNPJ unico e serve pra
validar nota fiscal contra a SEFAZ; esta aqui e um catalogo de marketing,
sem CNPJ, alimentado por uma rede de afiliados white-label (mockada por
enquanto, ver BeneficioAdapter).
"""
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE beneficios (
            beneficio_id           UUID PRIMARY KEY,
            nome                   VARCHAR(150) NOT NULL,
            tipo                   VARCHAR(20) NOT NULL CHECK (tipo IN ('desconto', 'cashback')),
            categoria              VARCHAR(50) NOT NULL,
            uso                    VARCHAR(20) NOT NULL CHECK (uso IN ('online', 'presencial')),
            descricao_oferta       VARCHAR(200) NOT NULL,
            percentual_referencia  NUMERIC(5,2),
            status                 VARCHAR(20) NOT NULL DEFAULT 'ativo',
            criado_em              TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX ix_beneficios_tipo_categoria ON beneficios (tipo, categoria, status);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE beneficios;")
