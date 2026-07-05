"""Consultas administrativas de usuarios -- so SQL, sem regra de negocio."""
import json
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row

_CADASTRO_COMPLETO_SQL = (
    "(nome IS NOT NULL AND celular IS NOT NULL AND data_nascimento IS NOT NULL "
    "AND cep IS NOT NULL AND numero IS NOT NULL)"
)


def _montar_filtros(
    busca: Optional[str],
    status: Optional[str],
    cadastro_completo: Optional[bool],
    tag: Optional[str],
) -> Tuple[str, dict]:
    condicoes = ["1 = 1"]
    params: dict = {}
    if busca:
        condicoes.append(
            "(lower(nome) LIKE :busca OR lower(email) LIKE :busca OR cpf LIKE :busca_cpf)"
        )
        params["busca"] = f"%{busca.lower()}%"
        params["busca_cpf"] = f"%{''.join(c for c in busca if c.isdigit())}%" if any(
            c.isdigit() for c in busca
        ) else "IMPOSSIVEL"
    if status:
        condicoes.append("status = :status")
        params["status"] = status
    if cadastro_completo is True:
        condicoes.append(_CADASTRO_COMPLETO_SQL)
    elif cadastro_completo is False:
        condicoes.append(f"NOT {_CADASTRO_COMPLETO_SQL}")
    if tag:
        condicoes.append("tags @> CAST(:tag AS jsonb)")
        params["tag"] = json.dumps([tag])
    return " AND ".join(condicoes), params


def list_usuarios(
    conn: Connection,
    busca: Optional[str],
    status: Optional[str],
    cadastro_completo: Optional[bool],
    tag: Optional[str],
    pagina: int,
    por_pagina: int,
) -> Tuple[List[Row], int]:
    where, params = _montar_filtros(busca, status, cadastro_completo, tag)
    total = conn.execute(
        text(f"SELECT COUNT(*) FROM wallet_accounts WHERE {where}"), params
    ).scalar()
    rows = conn.execute(
        text(
            f"""
            SELECT *, {_CADASTRO_COMPLETO_SQL} AS cadastro_completo
            FROM wallet_accounts
            WHERE {where}
            ORDER BY criado_em DESC
            LIMIT :limite OFFSET :offset
            """
        ),
        {**params, "limite": por_pagina, "offset": (pagina - 1) * por_pagina},
    ).all()
    return rows, total


def get_atividade(conn: Connection, account_id: UUID) -> Row:
    return conn.execute(
        text(
            """
            SELECT
                COALESCE((SELECT SUM(coins) FROM ledger_events WHERE account_id = :id), 0::numeric(14,2)) AS saldo_coins,
                (SELECT COUNT(*) FROM compras_capitalizacao WHERE account_id = :id AND status = 'confirmado') AS total_compras_confirmadas,
                COALESCE((SELECT SUM(valor_reais) FROM compras_capitalizacao WHERE account_id = :id AND status = 'confirmado'), 0::numeric(14,2)) AS total_valor_comprado,
                (SELECT COUNT(*) FROM beneficios_usos WHERE account_id = :id) AS total_beneficios_usados,
                (SELECT COUNT(*) FROM nf_submissoes WHERE account_id = :id) AS total_notas_enviadas,
                (SELECT COUNT(*) FROM resgates WHERE account_id = :id) AS total_resgates
            """
        ),
        {"id": str(account_id)},
    ).first()


def get_ultimos_eventos(conn: Connection, account_id: UUID, limite: int = 10) -> List[Row]:
    return conn.execute(
        text(
            """
            SELECT event_id, tipo_evento, coins, criado_em
            FROM ledger_events
            WHERE account_id = :id
            ORDER BY criado_em DESC
            LIMIT :limite
            """
        ),
        {"id": str(account_id), "limite": limite},
    ).all()


def atualizar_usuario(
    conn: Connection, account_id: UUID, status: Optional[str], tags: Optional[List[str]]
) -> Row:
    return conn.execute(
        text(
            f"""
            UPDATE wallet_accounts
            SET status = COALESCE(:status, status),
                tags = COALESCE(CAST(:tags AS jsonb), tags)
            WHERE account_id = :id
            RETURNING *, {_CADASTRO_COMPLETO_SQL} AS cadastro_completo
            """
        ),
        {
            "id": str(account_id),
            "status": status,
            "tags": json.dumps(tags) if tags is not None else None,
        },
    ).first()


def get_usuario(conn: Connection, account_id: UUID) -> Optional[Row]:
    return conn.execute(
        text(
            f"""
            SELECT *, {_CADASTRO_COMPLETO_SQL} AS cadastro_completo
            FROM wallet_accounts WHERE account_id = :id
            """
        ),
        {"id": str(account_id)},
    ).first()
