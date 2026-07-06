"""site_config: aparencia do app editavel pelo manager (rascunho -> publicado)

Fluxo "figma-like" do painel: o manager edita a linha 'rascunho' (e usa ela
pra renderizar o mockup de pre-visualizacao); o app le somente a linha
'publicado' via GET /v1/site-config. Publicar copia rascunho -> publicado e
grava um snapshot em site_config_publicacoes (auditoria e rollback manual).

O conteudo JSONB e livre de proposito: o contrato de campos (cores, textos,
ordem de secoes, banners do hero...) pertence aos frontends -- o backend so
armazena, versiona e publica, sem migration a cada campo novo.
"""
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE site_config (
            versao VARCHAR(20) PRIMARY KEY
                CHECK (versao IN ('rascunho', 'publicado')),
            conteudo JSONB NOT NULL DEFAULT '{}'::jsonb,
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            publicado_em timestamptz
        );
        """
    )
    op.execute("INSERT INTO site_config (versao) VALUES ('rascunho'), ('publicado');")
    op.execute(
        """
        CREATE TABLE site_config_publicacoes (
            publicacao_id UUID PRIMARY KEY,
            conteudo JSONB NOT NULL,
            publicado_em timestamptz NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE site_config_publicacoes;")
    op.execute("DROP TABLE site_config;")
