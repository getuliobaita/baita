"""Acesso a dados do motor de resgate -- so SQL, sem regra de negocio."""
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row


def get_catalogo_item(conn: Connection, item_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM catalogo_itens WHERE item_id = :id"), {"id": str(item_id)}
    ).first()


def insert_catalogo_item(
    conn: Connection, item_id: UUID, nome: str, custo_coins: Decimal, fornecedor: str
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO catalogo_itens (item_id, nome, custo_coins, fornecedor)
            VALUES (:item_id, :nome, :custo_coins, :fornecedor)
            RETURNING *
            """
        ),
        {"item_id": str(item_id), "nome": nome, "custo_coins": custo_coins, "fornecedor": fornecedor},
    ).first()


def get_soma_reservas_em_aberto(conn: Connection, account_id: UUID) -> Decimal:
    row = conn.execute(
        text(
            """
            SELECT COALESCE(SUM(coins_reservados), 0::numeric(14,2)) AS total
            FROM resgates
            WHERE account_id = :account_id AND status = 'reservado'
            """
        ),
        {"account_id": str(account_id)},
    ).first()
    return row.total


def insert_resgate(
    conn: Connection,
    resgate_id: UUID,
    account_id: UUID,
    catalogo_item_id: UUID,
    coins_reservados: Decimal,
    idempotency_key: str,
    fornecedor: str,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO resgates
                (resgate_id, account_id, catalogo_item_id, coins_reservados, idempotency_key, fornecedor)
            VALUES
                (:resgate_id, :account_id, :catalogo_item_id, :coins_reservados, :idempotency_key, :fornecedor)
            RETURNING *
            """
        ),
        {
            "resgate_id": str(resgate_id),
            "account_id": str(account_id),
            "catalogo_item_id": str(catalogo_item_id),
            "coins_reservados": coins_reservados,
            "idempotency_key": idempotency_key,
            "fornecedor": fornecedor,
        },
    ).first()


def get_resgate_by_idempotency_key(conn: Connection, idempotency_key: str) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM resgates WHERE idempotency_key = :key"), {"key": idempotency_key}
    ).first()


def get_resgate(conn: Connection, resgate_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM resgates WHERE resgate_id = :id"), {"id": str(resgate_id)}
    ).first()


def get_resgate_for_update(conn: Connection, resgate_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM resgates WHERE resgate_id = :id FOR UPDATE"), {"id": str(resgate_id)}
    ).first()


def atualizar_resgate_pedido_externo(conn: Connection, resgate_id: UUID, pedido_externo_id: str) -> Row:
    return conn.execute(
        text(
            """
            UPDATE resgates SET pedido_externo_id = :pedido_externo_id, atualizado_em = now()
            WHERE resgate_id = :id
            RETURNING *
            """
        ),
        {"pedido_externo_id": pedido_externo_id, "id": str(resgate_id)},
    ).first()


def confirmar_resgate(
    conn: Connection,
    resgate_id: UUID,
    event_id: UUID,
    codigo_entrega: Optional[str],
    instrucoes: Optional[str],
) -> Row:
    return conn.execute(
        text(
            """
            UPDATE resgates
            SET status = 'confirmado', event_id = :event_id, codigo_entrega = :codigo_entrega,
                instrucoes = :instrucoes, atualizado_em = now()
            WHERE resgate_id = :id
            RETURNING *
            """
        ),
        {
            "event_id": str(event_id),
            "codigo_entrega": codigo_entrega,
            "instrucoes": instrucoes,
            "id": str(resgate_id),
        },
    ).first()


def cancelar_resgate(conn: Connection, resgate_id: UUID, motivo: str) -> Row:
    return conn.execute(
        text(
            """
            UPDATE resgates SET status = 'cancelado', motivo_cancelamento = :motivo, atualizado_em = now()
            WHERE resgate_id = :id
            RETURNING *
            """
        ),
        {"motivo": motivo, "id": str(resgate_id)},
    ).first()
