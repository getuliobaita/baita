"""Acesso a dados de sorteios, numeros da sorte e apuracao -- so SQL."""
import json
import random
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row

from baita_coin.sorteios.apuracao import TOTAL_NUMEROS_SERIE
from baita_coin.sorteios.errors import SerieDeSorteioCheia


def get_sorteio_aberto_for_update(conn: Connection) -> Optional[Row]:
    return conn.execute(
        text(
            "SELECT * FROM sorteios WHERE status = 'aberto' ORDER BY criado_em ASC LIMIT 1 FOR UPDATE"
        )
    ).first()


def insert_sorteio(conn: Connection, sorteio_id: UUID, data_sorteio: datetime) -> Row:
    return conn.execute(
        text(
            "INSERT INTO sorteios (sorteio_id, data_sorteio) VALUES (:id, :data) RETURNING *"
        ),
        {"id": str(sorteio_id), "data": data_sorteio},
    ).first()


def insert_sorteio_completo(conn: Connection, sorteio_id: UUID, dados: dict) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO sorteios
                (sorteio_id, titulo, data_sorteio, periodo_inicio, periodo_fim,
                 data_apuracao, data_divulgacao, premios, banner_url)
            VALUES
                (:sorteio_id, :titulo, :data_sorteio, :periodo_inicio, :periodo_fim,
                 :data_apuracao, :data_divulgacao, CAST(:premios AS jsonb), :banner_url)
            RETURNING *
            """
        ),
        {"sorteio_id": str(sorteio_id), **dados},
    ).first()


def atualizar_sorteio(conn: Connection, sorteio_id: UUID, campos: dict) -> Row:
    """Atualiza apenas os campos fornecidos (os demais ficam intactos via
    COALESCE). `premios` chega como JSON string ou None."""
    return conn.execute(
        text(
            """
            UPDATE sorteios SET
                titulo          = COALESCE(:titulo, titulo),
                data_sorteio    = COALESCE(:data_sorteio, data_sorteio),
                periodo_inicio  = COALESCE(:periodo_inicio, periodo_inicio),
                periodo_fim     = COALESCE(:periodo_fim, periodo_fim),
                data_apuracao   = COALESCE(:data_apuracao, data_apuracao),
                data_divulgacao = COALESCE(:data_divulgacao, data_divulgacao),
                premios         = COALESCE(CAST(:premios AS jsonb), premios),
                banner_url      = COALESCE(:banner_url, banner_url),
                status          = COALESCE(:status, status)
            WHERE sorteio_id = :sorteio_id
            RETURNING *
            """
        ),
        {"sorteio_id": str(sorteio_id), **campos},
    ).first()


def get_sorteio(conn: Connection, sorteio_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM sorteios WHERE sorteio_id = :id"), {"id": str(sorteio_id)}
    ).first()


def get_sorteio_vigente(conn: Connection) -> Optional[Row]:
    """O sorteio aberto atual -- mesmo criterio de get_sorteio_aberto_for_update
    (o mais antigo aberto, pra onde os numeros novos vao), pra o app exibir
    exatamente a edicao em que o cliente esta concorrendo."""
    return conn.execute(
        text("SELECT * FROM sorteios WHERE status = 'aberto' ORDER BY criado_em ASC LIMIT 1")
    ).first()


def list_sorteios(conn: Connection) -> List[Row]:
    """Sorteios com contagem de numeros distribuidos e se ja tem apuracao --
    lista do painel para escolher qual apurar/auditar."""
    return conn.execute(
        text(
            """
            SELECT s.*,
                   (SELECT count(*) FROM numeros_sorte n
                    WHERE n.sorteio_id = s.sorteio_id AND n.status = 'ativo') AS total_numeros,
                   EXISTS(SELECT 1 FROM apuracoes a WHERE a.sorteio_id = s.sorteio_id) AS tem_apuracao
            FROM sorteios s
            ORDER BY s.data_sorteio DESC
            """
        )
    ).all()


# ---------------------------------------------------------------------------
# Numeros da sorte
# ---------------------------------------------------------------------------

_MAX_RODADAS_SORTEIO_NUMERO = 60


def emitir_numeros_sorte_aleatorios(
    conn: Connection,
    account_id: UUID,
    event_id: UUID,
    sorteio_id: UUID,
    quantidade: int,
    serie: int = 1,
) -> List[int]:
    """Emite `quantidade` numeros da sorte ALEATORIOS em [00000, 99999], nao
    repetidos na serie (regra 3.1.4 do regulamento).

    Sorteia candidatos distintos e insere com ON CONFLICT DO NOTHING contra a
    unicidade (sorteio_id, serie, numero); numeros ja tomados (por esta compra
    ou por transacoes concorrentes) sao pulados e um novo lote cobre o que
    faltou. Como o volume real (milhares/mes) e minusculo perto dos 100.000
    numeros da serie, colisoes sao raras e a convergencia e imediata.
    """
    emitidos: List[int] = []
    rodadas = 0
    while len(emitidos) < quantidade and rodadas < _MAX_RODADAS_SORTEIO_NUMERO:
        faltam = quantidade - len(emitidos)
        candidatos = random.sample(range(TOTAL_NUMEROS_SERIE), faltam)
        rows = conn.execute(
            text(
                """
                INSERT INTO numeros_sorte (account_id, event_id, sorteio_id, serie, numero)
                SELECT :account_id, :event_id, :sorteio_id, :serie, x
                FROM unnest(CAST(:candidatos AS integer[])) AS x
                ON CONFLICT (sorteio_id, serie, numero) DO NOTHING
                RETURNING numero
                """
            ),
            {
                "account_id": str(account_id),
                "event_id": str(event_id),
                "sorteio_id": str(sorteio_id),
                "serie": serie,
                "candidatos": candidatos,
            },
        ).all()
        emitidos.extend(r.numero for r in rows)
        rodadas += 1

    if len(emitidos) < quantidade:
        # Serie praticamente cheia (100.000 numeros) -- so alcancavel em
        # escala muito acima da atual. Rolagem para nova serie fica de
        # backlog; por ora, falha explicita e melhor que loop infinito.
        raise SerieDeSorteioCheia(
            "serie de numeros da sorte praticamente esgotada",
            detalhes={"sorteio_id": str(sorteio_id), "serie": serie},
        )
    return emitidos


def get_numeros_sorte_da_conta(
    conn: Connection, account_id: UUID, sorteio_id: Optional[UUID] = None
) -> List[Row]:
    filtro_sorteio = "AND n.sorteio_id = :sorteio_id" if sorteio_id else ""
    params = {"account_id": str(account_id)}
    if sorteio_id:
        params["sorteio_id"] = str(sorteio_id)
    return conn.execute(
        text(
            f"""
            SELECT n.numero, n.status, n.sorteio_id, n.criado_em, s.titulo,
                   s.data_sorteio, s.status AS sorteio_status
            FROM numeros_sorte n
            JOIN sorteios s ON s.sorteio_id = n.sorteio_id
            WHERE n.account_id = :account_id {filtro_sorteio}
            ORDER BY n.numero ASC
            """
        ),
        params,
    ).all()


def get_numeros_sorte_por_evento(conn: Connection, event_id: UUID) -> List[Row]:
    return conn.execute(
        text(
            "SELECT numero, sorteio_id FROM numeros_sorte WHERE event_id = :event_id ORDER BY numero ASC"
        ),
        {"event_id": str(event_id)},
    ).all()


# ---------------------------------------------------------------------------
# Apuracao do sorteio (auditavel)
# ---------------------------------------------------------------------------


def get_numeros_distribuidos(conn: Connection, sorteio_id: UUID, serie: int) -> List[Row]:
    """Todos os numeros ativos da serie, com o dono -- base da apuracao."""
    return conn.execute(
        text(
            """
            SELECT numero, account_id
            FROM numeros_sorte
            WHERE sorteio_id = :sorteio_id AND serie = :serie AND status = 'ativo'
            ORDER BY numero ASC
            """
        ),
        {"sorteio_id": str(sorteio_id), "serie": serie},
    ).all()


def get_dados_contato(conn: Connection, account_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT cpf, nome, celular, email FROM wallet_accounts WHERE account_id = :id"),
        {"id": str(account_id)},
    ).first()


def get_apuracao(conn: Connection, sorteio_id: UUID, serie: int) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM apuracoes WHERE sorteio_id = :sorteio_id AND serie = :serie"),
        {"sorteio_id": str(sorteio_id), "serie": serie},
    ).first()


def insert_apuracao(
    conn: Connection,
    apuracao_id: UUID,
    sorteio_id: UUID,
    serie: int,
    data_extracao,
    premios_loteria: list,
    numero_base: int,
    premios: list,
    total_distribuidos: int,
    resultado_hash: str,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO apuracoes
                (apuracao_id, sorteio_id, serie, data_extracao, premios_loteria,
                 numero_base, premios, total_distribuidos, resultado_hash)
            VALUES
                (:apuracao_id, :sorteio_id, :serie, :data_extracao, CAST(:premios_loteria AS jsonb),
                 :numero_base, CAST(:premios AS jsonb), :total_distribuidos, :resultado_hash)
            RETURNING *
            """
        ),
        {
            "apuracao_id": str(apuracao_id),
            "sorteio_id": str(sorteio_id),
            "serie": serie,
            "data_extracao": data_extracao,
            "premios_loteria": json.dumps([str(p) for p in premios_loteria]),
            "numero_base": numero_base,
            "premios": json.dumps([str(p) for p in premios]),
            "total_distribuidos": total_distribuidos,
            "resultado_hash": resultado_hash,
        },
    ).first()


def insert_contemplado(
    conn: Connection,
    contemplado_id: UUID,
    apuracao_id: UUID,
    ordem: int,
    numero_sorte: int,
    account_id: UUID,
    premio_valor: Decimal,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO apuracao_contemplados
                (contemplado_id, apuracao_id, ordem, numero_sorte, account_id, premio_valor)
            VALUES
                (:contemplado_id, :apuracao_id, :ordem, :numero_sorte, :account_id, :premio_valor)
            RETURNING *
            """
        ),
        {
            "contemplado_id": str(contemplado_id),
            "apuracao_id": str(apuracao_id),
            "ordem": ordem,
            "numero_sorte": numero_sorte,
            "account_id": str(account_id),
            "premio_valor": premio_valor,
        },
    ).first()


def get_contemplados(conn: Connection, apuracao_id: UUID) -> List[Row]:
    return conn.execute(
        text(
            """
            SELECT c.*, a.cpf, a.nome, a.celular, a.email
            FROM apuracao_contemplados c
            JOIN wallet_accounts a ON a.account_id = c.account_id
            WHERE c.apuracao_id = :apuracao_id
            ORDER BY c.ordem ASC
            """
        ),
        {"apuracao_id": str(apuracao_id)},
    ).all()
