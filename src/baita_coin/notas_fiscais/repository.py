"""Acesso a dados do pipeline de nota fiscal -- so SQL, sem regra de negocio."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row


def get_config(conn: Connection, chave: str) -> Dict[str, Any]:
    row = conn.execute(
        text("SELECT valor FROM config_operacional WHERE chave = :chave"), {"chave": chave}
    ).first()
    return row.valor


def get_parceiro_por_cnpj(conn: Connection, cnpj: str) -> Optional[Row]:
    return conn.execute(text("SELECT * FROM parceiros WHERE cnpj = :cnpj"), {"cnpj": cnpj}).first()


def list_submissoes(conn: Connection, status: Optional[str], limite: int):
    filtro = "WHERE s.status = :status" if status else ""
    return conn.execute(
        text(
            f"""
            SELECT s.*, a.cpf AS conta_cpf, p.nome_fantasia AS parceiro_nome
            FROM nf_submissoes s
            JOIN wallet_accounts a ON a.account_id = s.account_id
            LEFT JOIN parceiros p ON p.cnpj = s.cnpj_emitente
            {filtro}
            ORDER BY s.criado_em DESC
            LIMIT :limite
            """
        ),
        {"status": status, "limite": limite},
    ).all()


def insert_parceiro(
    conn: Connection, parceiro_id: UUID, cnpj: str, nome_fantasia: str, canal_nf: bool, canal_api: bool
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO parceiros (parceiro_id, cnpj, nome_fantasia, canal_nf, canal_api)
            VALUES (:parceiro_id, :cnpj, :nome_fantasia, :canal_nf, :canal_api)
            RETURNING *
            """
        ),
        {
            "parceiro_id": str(parceiro_id),
            "cnpj": cnpj,
            "nome_fantasia": nome_fantasia,
            "canal_nf": canal_nf,
            "canal_api": canal_api,
        },
    ).first()


def insert_regra_parceiro(
    conn: Connection,
    regra_id: UUID,
    parceiro_cnpj: str,
    vigencia_inicio: datetime,
    vigencia_fim: Optional[datetime],
    percentual_cashback: Decimal,
    teto_por_nota: Optional[Decimal],
    teto_por_cliente_mes: Optional[Decimal],
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO regras_parceiro
                (regra_id, parceiro_cnpj, vigencia_inicio, vigencia_fim, percentual_cashback, teto_por_nota, teto_por_cliente_mes)
            VALUES
                (:regra_id, :parceiro_cnpj, :vigencia_inicio, :vigencia_fim, :percentual_cashback, :teto_por_nota, :teto_por_cliente_mes)
            RETURNING *
            """
        ),
        {
            "regra_id": str(regra_id),
            "parceiro_cnpj": parceiro_cnpj,
            "vigencia_inicio": vigencia_inicio,
            "vigencia_fim": vigencia_fim,
            "percentual_cashback": percentual_cashback,
            "teto_por_nota": teto_por_nota,
            "teto_por_cliente_mes": teto_por_cliente_mes,
        },
    ).first()


def get_regra_parceiro_vigente(conn: Connection, parceiro_cnpj: str, momento: datetime) -> Optional[Row]:
    return conn.execute(
        text(
            """
            SELECT * FROM regras_parceiro
            WHERE parceiro_cnpj = :cnpj AND status = 'ativa' AND vigencia_inicio <= :momento
              AND (vigencia_fim IS NULL OR vigencia_fim > :momento)
            ORDER BY vigencia_inicio DESC
            LIMIT 1
            """
        ),
        {"cnpj": parceiro_cnpj, "momento": momento},
    ).first()


def get_submissao_by_idempotency_key(conn: Connection, idempotency_key: str) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM nf_submissoes WHERE idempotency_key = :key"), {"key": idempotency_key}
    ).first()


def get_submissao_by_chave_acesso(conn: Connection, chave_acesso: str) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM nf_submissoes WHERE chave_acesso = :chave"), {"chave": chave_acesso}
    ).first()


def get_submissao(conn: Connection, submissao_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM nf_submissoes WHERE submissao_id = :id"), {"id": str(submissao_id)}
    ).first()


def get_submissao_for_update(conn: Connection, submissao_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM nf_submissoes WHERE submissao_id = :id FOR UPDATE"), {"id": str(submissao_id)}
    ).first()


def insert_submissao(
    conn: Connection,
    submissao_id: UUID,
    account_id: UUID,
    idempotency_key: str,
    chave_acesso: Optional[str],
    uf: Optional[str],
    status: str,
    motivo_rejeicao: Optional[str],
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO nf_submissoes
                (submissao_id, account_id, idempotency_key, chave_acesso, uf, status, motivo_rejeicao)
            VALUES
                (:submissao_id, :account_id, :idempotency_key, :chave_acesso, :uf, :status, :motivo_rejeicao)
            RETURNING *
            """
        ),
        {
            "submissao_id": str(submissao_id),
            "account_id": str(account_id),
            "idempotency_key": idempotency_key,
            "chave_acesso": chave_acesso,
            "uf": uf,
            "status": status,
            "motivo_rejeicao": motivo_rejeicao,
        },
    ).first()


def rejeitar_submissao(
    conn: Connection,
    submissao_id: UUID,
    motivo_rejeicao: str,
    cnpj_emitente: Optional[str] = None,
    valor_total: Optional[Decimal] = None,
) -> Row:
    return conn.execute(
        text(
            """
            UPDATE nf_submissoes
            SET status = 'rejeitada', motivo_rejeicao = :motivo, cnpj_emitente = :cnpj,
                valor_total = :valor, processado_em = now()
            WHERE submissao_id = :id
            RETURNING *
            """
        ),
        {
            "motivo": motivo_rejeicao,
            "cnpj": cnpj_emitente,
            "valor": valor_total,
            "id": str(submissao_id),
        },
    ).first()


def creditar_submissao(
    conn: Connection, submissao_id: UUID, event_id: UUID, cnpj_emitente: str, valor_total: Decimal
) -> Row:
    return conn.execute(
        text(
            """
            UPDATE nf_submissoes
            SET status = 'creditada', event_id = :event_id, cnpj_emitente = :cnpj,
                valor_total = :valor, processado_em = now()
            WHERE submissao_id = :id
            RETURNING *
            """
        ),
        {"event_id": str(event_id), "cnpj": cnpj_emitente, "valor": valor_total, "id": str(submissao_id)},
    ).first()


def get_total_creditado_hoje(conn: Connection, account_id: UUID, agora: datetime) -> Decimal:
    row = conn.execute(
        text(
            """
            SELECT COALESCE(SUM(valor_total), 0::numeric(14,2)) AS total
            FROM nf_submissoes
            WHERE account_id = :account_id AND status = 'creditada'
              AND processado_em >= date_trunc('day', CAST(:agora AS timestamptz))
              AND processado_em < date_trunc('day', CAST(:agora AS timestamptz)) + INTERVAL '1 day'
            """
        ),
        {"account_id": str(account_id), "agora": agora},
    ).first()
    return row.total


def get_total_creditado_mes_parceiro(
    conn: Connection, account_id: UUID, cnpj_emitente: str, agora: datetime
) -> Decimal:
    row = conn.execute(
        text(
            """
            SELECT COALESCE(SUM(valor_total), 0::numeric(14,2)) AS total
            FROM nf_submissoes
            WHERE account_id = :account_id AND cnpj_emitente = :cnpj AND status = 'creditada'
              AND processado_em >= date_trunc('month', CAST(:agora AS timestamptz))
              AND processado_em < date_trunc('month', CAST(:agora AS timestamptz)) + INTERVAL '1 month'
            """
        ),
        {"account_id": str(account_id), "cnpj": cnpj_emitente, "agora": agora},
    ).first()
    return row.total
