"""Acesso a dados das assinaturas -- so SQL, sem regra de negocio."""
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row


def insert_assinatura(
    conn: Connection,
    assinatura_id: UUID,
    account_id: UUID,
    quantidade_pacotes: int,
    valor_reais: Decimal,
    idempotency_key: str,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO assinaturas
                (assinatura_id, account_id, quantidade_pacotes, valor_reais, idempotency_key)
            VALUES
                (:assinatura_id, :account_id, :quantidade_pacotes, :valor_reais, :idempotency_key)
            RETURNING *
            """
        ),
        {
            "assinatura_id": str(assinatura_id),
            "account_id": str(account_id),
            "quantidade_pacotes": quantidade_pacotes,
            "valor_reais": valor_reais,
            "idempotency_key": idempotency_key,
        },
    ).first()


def get_assinatura(conn: Connection, assinatura_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM assinaturas WHERE assinatura_id = :id"), {"id": str(assinatura_id)}
    ).first()


def get_assinatura_by_idempotency_key(conn: Connection, idempotency_key: str) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM assinaturas WHERE idempotency_key = :key"), {"key": idempotency_key}
    ).first()


def get_assinatura_by_gateway_id(conn: Connection, gateway_subscription_id: str) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM assinaturas WHERE gateway_subscription_id = :gid"),
        {"gid": gateway_subscription_id},
    ).first()


def get_assinatura_vigente_da_conta(conn: Connection, account_id: UUID) -> Optional[Row]:
    """Assinatura nao-cancelada mais recente da conta (ativa, aguardando ou
    inadimplente -- todas bloqueiam a criacao de uma segunda)."""
    return conn.execute(
        text(
            """
            SELECT * FROM assinaturas
            WHERE account_id = :account_id AND status != 'cancelada'
            ORDER BY criado_em DESC LIMIT 1
            """
        ),
        {"account_id": str(account_id)},
    ).first()


def atualizar_assinatura(conn: Connection, assinatura_id: UUID, campos: dict) -> Row:
    return conn.execute(
        text(
            """
            UPDATE assinaturas SET
                status = COALESCE(:status, status),
                gateway_subscription_id = COALESCE(:gateway_subscription_id, gateway_subscription_id),
                cartao_bandeira = COALESCE(:cartao_bandeira, cartao_bandeira),
                cartao_ultimos4 = COALESCE(:cartao_ultimos4, cartao_ultimos4),
                cancelada_em = COALESCE(:cancelada_em, cancelada_em),
                atualizado_em = now()
            WHERE assinatura_id = :assinatura_id
            RETURNING *
            """
        ),
        {
            "assinatura_id": str(assinatura_id),
            "status": campos.get("status"),
            "gateway_subscription_id": campos.get("gateway_subscription_id"),
            "cartao_bandeira": campos.get("cartao_bandeira"),
            "cartao_ultimos4": campos.get("cartao_ultimos4"),
            "cancelada_em": campos.get("cancelada_em"),
        },
    ).first()
