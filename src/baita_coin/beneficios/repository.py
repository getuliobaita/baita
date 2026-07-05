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
    custo_em_coins: Decimal,
    logo_url: Optional[str] = None,
    imagem_capa_url: Optional[str] = None,
    chamada: Optional[str] = None,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO beneficios
                (beneficio_id, nome, tipo, categoria, uso, descricao_oferta, percentual_referencia,
                 custo_em_coins, logo_url, imagem_capa_url, chamada)
            VALUES
                (:beneficio_id, :nome, :tipo, :categoria, :uso, :descricao_oferta, :percentual_referencia,
                 :custo_em_coins, :logo_url, :imagem_capa_url, :chamada)
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
            "custo_em_coins": custo_em_coins,
            "logo_url": logo_url,
            "imagem_capa_url": imagem_capa_url,
            "chamada": chamada,
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


def list_beneficios_admin(
    conn: Connection, tipo: Optional[str] = None, categoria: Optional[str] = None
) -> List[Row]:
    """Uso administrativo -- inclui inativos, diferente de list_beneficios
    (publico, so mostra ativos)."""
    condicoes = ["1 = 1"]
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


def atualizar_beneficio(
    conn: Connection,
    beneficio_id: UUID,
    nome: Optional[str],
    categoria: Optional[str],
    uso: Optional[str],
    descricao_oferta: Optional[str],
    percentual_referencia: Optional[Decimal],
    custo_em_coins: Optional[Decimal],
    status: Optional[str],
    logo_url: Optional[str] = None,
    imagem_capa_url: Optional[str] = None,
    chamada: Optional[str] = None,
) -> Row:
    return conn.execute(
        text(
            """
            UPDATE beneficios
            SET nome = COALESCE(:nome, nome),
                categoria = COALESCE(:categoria, categoria),
                uso = COALESCE(:uso, uso),
                descricao_oferta = COALESCE(:descricao_oferta, descricao_oferta),
                percentual_referencia = COALESCE(:percentual_referencia, percentual_referencia),
                custo_em_coins = COALESCE(:custo_em_coins, custo_em_coins),
                status = COALESCE(:status, status),
                logo_url = COALESCE(:logo_url, logo_url),
                imagem_capa_url = COALESCE(:imagem_capa_url, imagem_capa_url),
                chamada = COALESCE(:chamada, chamada)
            WHERE beneficio_id = :beneficio_id
            RETURNING *
            """
        ),
        {
            "beneficio_id": str(beneficio_id),
            "nome": nome,
            "categoria": categoria,
            "uso": uso,
            "descricao_oferta": descricao_oferta,
            "percentual_referencia": percentual_referencia,
            "custo_em_coins": custo_em_coins,
            "status": status,
            "logo_url": logo_url,
            "imagem_capa_url": imagem_capa_url,
            "chamada": chamada,
        },
    ).first()


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
