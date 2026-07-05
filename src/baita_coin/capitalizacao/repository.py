"""Acesso a dados do motor de capitalizacao -- so SQL, sem regra de negocio."""
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row


def get_relatorio_compradores(conn: Connection) -> Row:
    """'Recorrente' = ja fez 2+ compras confirmadas, sem janela de tempo
    fixa (metrica simples de recompra historica, confirmada com o usuario)."""
    return conn.execute(
        text(
            """
            WITH compras_por_conta AS (
                SELECT account_id, COUNT(*) AS qtd_compras, COALESCE(SUM(valor_reais), 0) AS valor_total
                FROM compras_capitalizacao
                WHERE status = 'confirmado'
                GROUP BY account_id
            )
            SELECT
                COUNT(*) AS total_compradores_unicos,
                COUNT(*) FILTER (WHERE qtd_compras >= 2) AS compradores_recorrentes,
                COALESCE(SUM(qtd_compras), 0) AS total_compras_confirmadas,
                COALESCE(SUM(valor_total), 0::numeric(14,2)) AS total_valor_reais_comprado
            FROM compras_por_conta
            """
        )
    ).first()


def get_regra_vigente(conn: Connection, momento: datetime) -> Optional[Row]:
    return conn.execute(
        text(
            """
            SELECT * FROM regras_capitalizacao
            WHERE status = 'ativa' AND vigencia_inicio <= :momento
              AND (vigencia_fim IS NULL OR vigencia_fim > :momento)
            ORDER BY vigencia_inicio DESC
            LIMIT 1
            """
        ),
        {"momento": momento},
    ).first()


def get_campanhas_ativas_gerais(conn: Connection, momento: datetime) -> List[Row]:
    """Campanhas de escopo geral (escopo_parceiro NULL) -- as unicas que
    valem pra capitalizacao, per secao 4.5 da spec."""
    return conn.execute(
        text(
            """
            SELECT * FROM campanhas_multiplicador
            WHERE status = 'ativa' AND escopo_parceiro IS NULL
              AND vigencia_inicio <= :momento AND vigencia_fim > :momento
            """
        ),
        {"momento": momento},
    ).all()


def get_campanha(conn: Connection, campanha_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM campanhas_multiplicador WHERE campanha_id = :id"), {"id": str(campanha_id)}
    ).first()


def list_campanhas(conn: Connection) -> List[Row]:
    """Todas as campanhas, qualquer status/vigencia -- uso administrativo
    (a listagem publica em get_campanhas_ativas_gerais so mostra as vigentes)."""
    return conn.execute(text("SELECT * FROM campanhas_multiplicador ORDER BY criado_em DESC")).all()


def atualizar_campanha(
    conn: Connection,
    campanha_id: UUID,
    nome: Optional[str],
    multiplicador: Optional[Decimal],
    vigencia_fim: Optional[datetime],
    prioridade: Optional[int],
    status: Optional[str],
) -> Row:
    return conn.execute(
        text(
            """
            UPDATE campanhas_multiplicador
            SET nome = COALESCE(:nome, nome),
                multiplicador = COALESCE(:multiplicador, multiplicador),
                vigencia_fim = COALESCE(:vigencia_fim, vigencia_fim),
                prioridade = COALESCE(:prioridade, prioridade),
                status = COALESCE(:status, status)
            WHERE campanha_id = :campanha_id
            RETURNING *
            """
        ),
        {
            "campanha_id": str(campanha_id),
            "nome": nome,
            "multiplicador": multiplicador,
            "vigencia_fim": vigencia_fim,
            "prioridade": prioridade,
            "status": status,
        },
    ).first()


def insert_campanha(
    conn: Connection,
    campanha_id: UUID,
    nome: str,
    multiplicador: Decimal,
    vigencia_inicio: datetime,
    vigencia_fim: datetime,
    prioridade: int,
    escopo_parceiro: Optional[UUID],
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO campanhas_multiplicador
                (campanha_id, nome, multiplicador, vigencia_inicio, vigencia_fim, prioridade, escopo_parceiro)
            VALUES
                (:campanha_id, :nome, :multiplicador, :vigencia_inicio, :vigencia_fim, :prioridade, :escopo_parceiro)
            RETURNING *
            """
        ),
        {
            "campanha_id": str(campanha_id),
            "nome": nome,
            "multiplicador": multiplicador,
            "vigencia_inicio": vigencia_inicio,
            "vigencia_fim": vigencia_fim,
            "prioridade": prioridade,
            "escopo_parceiro": str(escopo_parceiro) if escopo_parceiro else None,
        },
    ).first()


def insert_compra(
    conn: Connection,
    compra_id: UUID,
    account_id: UUID,
    quantidade_pacotes: int,
    valor_reais: Decimal,
    idempotency_key: str,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO compras_capitalizacao
                (compra_id, account_id, quantidade_pacotes, valor_reais, idempotency_key)
            VALUES
                (:compra_id, :account_id, :quantidade_pacotes, :valor_reais, :idempotency_key)
            RETURNING *
            """
        ),
        {
            "compra_id": str(compra_id),
            "account_id": str(account_id),
            "quantidade_pacotes": quantidade_pacotes,
            "valor_reais": valor_reais,
            "idempotency_key": idempotency_key,
        },
    ).first()


def get_compra_by_idempotency_key(conn: Connection, idempotency_key: str) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM compras_capitalizacao WHERE idempotency_key = :key"),
        {"key": idempotency_key},
    ).first()


def get_compra(conn: Connection, compra_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM compras_capitalizacao WHERE compra_id = :id"),
        {"id": str(compra_id)},
    ).first()


def get_compra_for_update(conn: Connection, compra_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM compras_capitalizacao WHERE compra_id = :id FOR UPDATE"),
        {"id": str(compra_id)},
    ).first()


def atualizar_compra_gateway_info(
    conn: Connection, compra_id: UUID, gateway: str, gateway_transaction_id: str
) -> None:
    conn.execute(
        text(
            "UPDATE compras_capitalizacao SET gateway = :gateway, gateway_transaction_id = :gtid "
            "WHERE compra_id = :id"
        ),
        {"gateway": gateway, "gtid": gateway_transaction_id, "id": str(compra_id)},
    )


def confirmar_compra(conn: Connection, compra_id: UUID, event_id: UUID) -> Row:
    return conn.execute(
        text(
            """
            UPDATE compras_capitalizacao
            SET status = 'confirmado', event_id = :event_id, atualizado_em = now()
            WHERE compra_id = :id
            RETURNING *
            """
        ),
        {"event_id": str(event_id), "id": str(compra_id)},
    ).first()


def rejeitar_compra(conn: Connection, compra_id: UUID, motivo: str) -> Row:
    return conn.execute(
        text(
            """
            UPDATE compras_capitalizacao
            SET status = 'rejeitado', motivo_rejeicao = :motivo, atualizado_em = now()
            WHERE compra_id = :id
            RETURNING *
            """
        ),
        {"motivo": motivo, "id": str(compra_id)},
    ).first()


def get_sorteio_aberto_for_update(conn: Connection) -> Optional[Row]:
    return conn.execute(
        text(
            "SELECT * FROM sorteios WHERE status = 'aberto' ORDER BY criado_em ASC LIMIT 1 FOR UPDATE"
        )
    ).first()


def reservar_faixa_numeros(conn: Connection, sorteio_id: UUID, quantidade: int) -> Row:
    """Incrementa o contador do sorteio de forma atomica e devolve o
    intervalo [numero_inicial, numero_final] reservado pra esta compra."""
    return conn.execute(
        text(
            """
            UPDATE sorteios
            SET proximo_numero_disponivel = proximo_numero_disponivel + :quantidade
            WHERE sorteio_id = :sorteio_id
            RETURNING
                (proximo_numero_disponivel - :quantidade) AS numero_inicial,
                (proximo_numero_disponivel - 1) AS numero_final
            """
        ),
        {"sorteio_id": str(sorteio_id), "quantidade": quantidade},
    ).first()


def insert_sorteio(conn: Connection, sorteio_id: UUID, data_sorteio: datetime) -> Row:
    return conn.execute(
        text(
            "INSERT INTO sorteios (sorteio_id, data_sorteio) VALUES (:id, :data) RETURNING *"
        ),
        {"id": str(sorteio_id), "data": data_sorteio},
    ).first()


def insert_numero_sorte_faixa(
    conn: Connection,
    faixa_id: UUID,
    account_id: UUID,
    event_id: UUID,
    sorteio_id: UUID,
    numero_inicial: int,
    numero_final: int,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO numeros_sorte_faixas
                (faixa_id, account_id, event_id, sorteio_id, numero_inicial, numero_final)
            VALUES
                (:faixa_id, :account_id, :event_id, :sorteio_id, :numero_inicial, :numero_final)
            RETURNING *
            """
        ),
        {
            "faixa_id": str(faixa_id),
            "account_id": str(account_id),
            "event_id": str(event_id),
            "sorteio_id": str(sorteio_id),
            "numero_inicial": numero_inicial,
            "numero_final": numero_final,
        },
    ).first()


def insert_capitalizacao_titulo(
    conn: Connection,
    titulo_id: UUID,
    event_id: UUID,
    numero_titulo_susep: str,
    plano_id: str,
    valor_pago: Decimal,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO capitalizacao_titulos (titulo_id, event_id, numero_titulo_susep, plano_id, valor_pago)
            VALUES (:titulo_id, :event_id, :numero_titulo_susep, :plano_id, :valor_pago)
            RETURNING *
            """
        ),
        {
            "titulo_id": str(titulo_id),
            "event_id": str(event_id),
            "numero_titulo_susep": numero_titulo_susep,
            "plano_id": plano_id,
            "valor_pago": valor_pago,
        },
    ).first()


def get_numeros_sorte_por_sorteio(conn: Connection, account_id: UUID, sorteio_id: UUID) -> List[Row]:
    return conn.execute(
        text(
            """
            SELECT * FROM numeros_sorte_faixas
            WHERE account_id = :account_id AND sorteio_id = :sorteio_id
            ORDER BY numero_inicial ASC
            """
        ),
        {"account_id": str(account_id), "sorteio_id": str(sorteio_id)},
    ).all()


def get_sorteio(conn: Connection, sorteio_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM sorteios WHERE sorteio_id = :id"), {"id": str(sorteio_id)}
    ).first()


def get_titulo_por_evento(conn: Connection, event_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM capitalizacao_titulos WHERE event_id = :event_id"),
        {"event_id": str(event_id)},
    ).first()


def get_numero_sorte_faixa_por_evento(conn: Connection, event_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM numeros_sorte_faixas WHERE event_id = :event_id"),
        {"event_id": str(event_id)},
    ).first()
