"""Acesso a dados do catalogo de beneficios -- so SQL, sem regra de negocio."""
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row


def insert_beneficio(
    conn: Connection,
    beneficio_id: UUID,
    nome: str,
    tipo: str,
    categoria: str,
    uso: str,
    descricao_oferta: str,
    percentual_referencia: Optional[Decimal],
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO beneficios (beneficio_id, nome, tipo, categoria, uso, descricao_oferta, percentual_referencia)
            VALUES (:beneficio_id, :nome, :tipo, :categoria, :uso, :descricao_oferta, :percentual_referencia)
            RETURNING *
            """
        ),
        {
            "beneficio_id": str(beneficio_id),
            "nome": nome,
            "tipo": tipo,
            "categoria": categoria,
            "uso": uso,
            "descricao_oferta": descricao_oferta,
            "percentual_referencia": percentual_referencia,
        },
    ).first()


def get_beneficio(conn: Connection, beneficio_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM beneficios WHERE beneficio_id = :id"), {"id": str(beneficio_id)}
    ).first()


def list_beneficios(
    conn: Connection, tipo: Optional[str] = None, categoria: Optional[str] = None
) -> List[Row]:
    condicoes = ["status = 'ativo'"]
    params = {}
    if tipo is not None:
        condicoes.append("tipo = :tipo")
        params["tipo"] = tipo
    if categoria is not None:
        condicoes.append("categoria = :categoria")
        params["categoria"] = categoria
    where = " AND ".join(condicoes)
    return conn.execute(
        text(f"SELECT * FROM beneficios WHERE {where} ORDER BY nome ASC"), params
    ).all()


def get_uso_by_idempotency_key(conn: Connection, idempotency_key: str) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM beneficios_usos WHERE idempotency_key = :key"), {"key": idempotency_key}
    ).first()


def insert_uso(
    conn: Connection,
    uso_id: UUID,
    account_id: UUID,
    beneficio_id: UUID,
    event_id: UUID,
    idempotency_key: str,
    codigo_cupom: Optional[str],
    link_afiliado: Optional[str],
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO beneficios_usos
                (uso_id, account_id, beneficio_id, event_id, idempotency_key, codigo_cupom, link_afiliado)
            VALUES
                (:uso_id, :account_id, :beneficio_id, :event_id, :idempotency_key, :codigo_cupom, :link_afiliado)
            RETURNING *
            """
        ),
        {
            "uso_id": str(uso_id),
            "account_id": str(account_id),
            "beneficio_id": str(beneficio_id),
            "event_id": str(event_id),
            "idempotency_key": idempotency_key,
            "codigo_cupom": codigo_cupom,
            "link_afiliado": link_afiliado,
        },
    ).first()
