"""numeros_sorte individuais (substitui as faixas)

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-06

Decisao do usuario: cada numero da sorte e um registro individual, nao uma
faixa. A modelagem por faixa vinha da spec original (regra de 1 numero por
coin, onde uma compra podia gerar milhares de numeros); com a regra atual
de 1 numero a cada 20 coins, o volume por compra e pequeno (1-200) e a
individualizacao simplifica exibicao, sorteio e contemplacao por numero.

Os dados existentes sao convertidos expandindo cada faixa com
generate_series antes de dropar a tabela antiga.
"""
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE numeros_sorte (
            numero_sorte_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sorteio_id       UUID NOT NULL REFERENCES sorteios(sorteio_id),
            account_id       UUID NOT NULL REFERENCES wallet_accounts(account_id),
            event_id         UUID NOT NULL REFERENCES ledger_events(event_id),
            numero           BIGINT NOT NULL,
            status           VARCHAR(20) NOT NULL DEFAULT 'ativo',
            criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (sorteio_id, numero)
        );

        CREATE INDEX ix_numeros_sorte_account ON numeros_sorte (account_id, sorteio_id);
        CREATE INDEX ix_numeros_sorte_event ON numeros_sorte (event_id);

        -- converte as faixas existentes em numeros individuais
        INSERT INTO numeros_sorte (sorteio_id, account_id, event_id, numero, status, criado_em)
        SELECT f.sorteio_id, f.account_id, f.event_id, gs.numero, f.status, f.criado_em
        FROM numeros_sorte_faixas f
        CROSS JOIN LATERAL generate_series(f.numero_inicial, f.numero_final) AS gs(numero);

        DROP TABLE numeros_sorte_faixas;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE numeros_sorte_faixas (
            faixa_id         UUID PRIMARY KEY,
            account_id       UUID NOT NULL REFERENCES wallet_accounts(account_id),
            event_id         UUID NOT NULL UNIQUE REFERENCES ledger_events(event_id),
            sorteio_id       UUID NOT NULL REFERENCES sorteios(sorteio_id),
            numero_inicial   BIGINT NOT NULL,
            numero_final     BIGINT NOT NULL CHECK (numero_final >= numero_inicial),
            status           VARCHAR(20) NOT NULL DEFAULT 'ativo',
            criado_em        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        INSERT INTO numeros_sorte_faixas (faixa_id, account_id, event_id, sorteio_id, numero_inicial, numero_final, status)
        SELECT gen_random_uuid(), account_id, event_id, sorteio_id, MIN(numero), MAX(numero), MIN(status)
        FROM numeros_sorte
        GROUP BY account_id, event_id, sorteio_id;

        DROP TABLE numeros_sorte;
        """
    )
