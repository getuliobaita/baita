"""numeros da sorte aleatorios (00000-99999) + apuracao auditavel do sorteio

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-07

Duas mudancas, alinhadas ao regulamento (Modalidade Incentivo, SUSEP):

1. Numero da Sorte passa a ser aleatorio em [00.000, 99.999], nao repetido
   por serie de 100.000 (regra 3.1.3/3.1.4). Antes era sequencial (1,2,3...),
   um placeholder. Adiciona coluna `serie` e troca a unicidade para
   (sorteio_id, serie, numero). Numeros ja emitidos (poucos, pre-lancamento)
   sao mantidos como estao -- so os novos usam a distribuicao aleatoria.

2. Apuracao AUDITAVEL: tabelas `apuracoes` e `apuracao_contemplados`,
   append-only (trigger de imutabilidade, mesma filosofia do ledger). Uma
   apuracao guarda a entrada (5 premios da Loteria Federal), o numero base
   calculado, os contemplados e um hash de integridade -- para que uma
   auditoria reproduza e confira o resultado.
"""
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        -- 1. numero da sorte aleatorio por serie -------------------------
        ALTER TABLE numeros_sorte ADD COLUMN serie INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE numeros_sorte DROP CONSTRAINT numeros_sorte_sorteio_id_numero_key;
        ALTER TABLE numeros_sorte ADD CONSTRAINT numeros_sorte_sorteio_serie_numero_key
            UNIQUE (sorteio_id, serie, numero);
        ALTER TABLE numeros_sorte ADD CONSTRAINT numeros_sorte_faixa_valida
            CHECK (numero BETWEEN 0 AND 99999);

        -- 2. apuracao auditavel ------------------------------------------
        CREATE TABLE apuracoes (
            apuracao_id        UUID PRIMARY KEY,
            sorteio_id         UUID NOT NULL REFERENCES sorteios(sorteio_id),
            serie              INTEGER NOT NULL DEFAULT 1,
            data_extracao      DATE NOT NULL,
            premios_loteria    JSONB NOT NULL,
            numero_base        INTEGER NOT NULL CHECK (numero_base BETWEEN 0 AND 99999),
            premios            JSONB NOT NULL,
            total_distribuidos INTEGER NOT NULL,
            resultado_hash     TEXT NOT NULL,
            criado_em          TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (sorteio_id, serie)
        );

        CREATE TABLE apuracao_contemplados (
            contemplado_id  UUID PRIMARY KEY,
            apuracao_id     UUID NOT NULL REFERENCES apuracoes(apuracao_id),
            ordem           INTEGER NOT NULL,
            numero_sorte    INTEGER NOT NULL,
            account_id      UUID NOT NULL REFERENCES wallet_accounts(account_id),
            premio_valor    NUMERIC(14,2) NOT NULL,
            criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (apuracao_id, ordem)
        );

        CREATE INDEX ix_apuracao_contemplados_apuracao ON apuracao_contemplados (apuracao_id);

        -- imutabilidade: uma apuracao registrada nunca muda nem some (auditoria)
        CREATE FUNCTION apuracao_forbid_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'apuracao e imutavel (auditoria): % nao e permitido em %',
                TG_OP, TG_TABLE_NAME;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_apuracoes_immutable
            BEFORE UPDATE OR DELETE ON apuracoes
            FOR EACH ROW EXECUTE FUNCTION apuracao_forbid_mutation();

        CREATE TRIGGER trg_apuracao_contemplados_immutable
            BEFORE UPDATE OR DELETE ON apuracao_contemplados
            FOR EACH ROW EXECUTE FUNCTION apuracao_forbid_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_apuracao_contemplados_immutable ON apuracao_contemplados;
        DROP TRIGGER IF EXISTS trg_apuracoes_immutable ON apuracoes;
        DROP FUNCTION IF EXISTS apuracao_forbid_mutation();
        DROP TABLE IF EXISTS apuracao_contemplados;
        DROP TABLE IF EXISTS apuracoes;

        ALTER TABLE numeros_sorte DROP CONSTRAINT numeros_sorte_faixa_valida;
        ALTER TABLE numeros_sorte DROP CONSTRAINT numeros_sorte_sorteio_serie_numero_key;
        ALTER TABLE numeros_sorte ADD CONSTRAINT numeros_sorte_sorteio_id_numero_key
            UNIQUE (sorteio_id, numero);
        ALTER TABLE numeros_sorte DROP COLUMN serie;
        """
    )
