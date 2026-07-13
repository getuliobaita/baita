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


def atualizar_usuario(conn: Connection, account_id: UUID, campos: dict) -> Row:
    """Edicao administrativa: SOBRESCREVE os campos fornecidos (o fluxo do
    app so completa vazios; o painel e autoritativo). Campos ausentes (None)
    ficam intactos via COALESCE. Inclui correcao de CPF."""
    return conn.execute(
        text(
            f"""
            UPDATE wallet_accounts
            SET status = COALESCE(:status, status),
                tags = COALESCE(CAST(:tags AS jsonb), tags),
                cpf = COALESCE(:cpf, cpf),
                nome = COALESCE(:nome, nome),
                email = COALESCE(:email, email),
                celular = COALESCE(:celular, celular),
                data_nascimento = COALESCE(:data_nascimento, data_nascimento),
                cep = COALESCE(:cep, cep),
                logradouro = COALESCE(:logradouro, logradouro),
                numero = COALESCE(:numero, numero),
                complemento = COALESCE(:complemento, complemento),
                bairro = COALESCE(:bairro, bairro),
                cidade = COALESCE(:cidade, cidade),
                uf = COALESCE(:uf, uf)
            WHERE account_id = :id
            RETURNING *, {_CADASTRO_COMPLETO_SQL} AS cadastro_completo
            """
        ),
        {
            "id": str(account_id),
            "status": campos.get("status"),
            "tags": json.dumps(campos["tags"]) if campos.get("tags") is not None else None,
            "cpf": campos.get("cpf"),
            "nome": campos.get("nome"),
            "email": campos.get("email"),
            "celular": campos.get("celular"),
            "data_nascimento": campos.get("data_nascimento"),
            "cep": campos.get("cep"),
            "logradouro": campos.get("logradouro"),
            "numero": campos.get("numero"),
            "complemento": campos.get("complemento"),
            "bairro": campos.get("bairro"),
            "cidade": campos.get("cidade"),
            "uf": campos.get("uf"),
        },
    ).first()


def list_para_export(conn: Connection, apenas_opt_in_email: bool) -> List[Row]:
    """Base pra exportacao de comunicacoes. Sem CPF (minimizacao de dados):
    a ferramenta de e-mail so precisa de nome/e-mail/segmentos."""
    filtro = (
        "AND aceita_comunicacoes_email = true AND email IS NOT NULL"
        if apenas_opt_in_email
        else ""
    )
    return conn.execute(
        text(
            f"""
            SELECT account_id, nome, email, celular, status, tags,
                   aceita_comunicacoes_email, aceita_comunicacoes_push, criado_em
            FROM wallet_accounts
            WHERE status = 'ativa' {filtro}
            ORDER BY criado_em ASC
            """
        )
    ).all()


def registrar_alteracao(conn: Connection, account_id: UUID, acao: str, campos: dict) -> None:
    """Trilha de auditoria imutavel de toda acao administrativa no cadastro."""
    conn.execute(
        text(
            """
            INSERT INTO admin_usuarios_alteracoes (account_id, acao, campos)
            VALUES (:account_id, :acao, CAST(:campos AS jsonb))
            """
        ),
        {
            "account_id": str(account_id),
            "acao": acao,
            "campos": json.dumps({k: str(v) for k, v in campos.items() if v is not None}),
        },
    )


def list_alteracoes(conn: Connection, account_id: UUID) -> List[Row]:
    return conn.execute(
        text(
            "SELECT * FROM admin_usuarios_alteracoes WHERE account_id = :id ORDER BY criado_em DESC"
        ),
        {"id": str(account_id)},
    ).all()


def contar_movimentacoes(conn: Connection, account_id: UUID) -> int:
    return conn.execute(
        text("SELECT count(*) FROM ledger_events WHERE account_id = :id"),
        {"id": str(account_id)},
    ).scalar()


def excluir_usuario_sem_movimentacoes(conn: Connection, account_id: UUID) -> None:
    """Exclusao fisica de uma conta SEM movimentacoes de coins (validar com
    contar_movimentacoes antes). Remove os vinculos que nao tem lastro no
    ledger; a trilha de auditoria administrativa fica (nao tem FK e e o
    registro historico da exclusao)."""
    aid = {"id": str(account_id)}
    conn.execute(text("UPDATE beneficios_cupons SET account_id = NULL, atribuido_em = NULL WHERE account_id = :id"), aid)
    conn.execute(text("DELETE FROM beneficios_usos WHERE account_id = :id AND event_id IS NULL"), aid)
    conn.execute(
        text(
            "DELETE FROM notas_servico WHERE compra_id IN "
            "(SELECT compra_id FROM compras_capitalizacao WHERE account_id = :id)"
        ),
        aid,
    )
    conn.execute(text("DELETE FROM nf_submissoes WHERE account_id = :id"), aid)
    conn.execute(text("DELETE FROM compras_capitalizacao WHERE account_id = :id"), aid)
    conn.execute(text("DELETE FROM resgates WHERE account_id = :id"), aid)
    conn.execute(text("DELETE FROM assinaturas WHERE account_id = :id"), aid)
    conn.execute(text("DELETE FROM wallet_accounts WHERE account_id = :id"), aid)


def reset_dados_usuarios(conn: Connection) -> int:
    """Apaga TODOS os cadastros e dados transacionais (uso pre-lancamento,
    protegido por env + confirmacao). Preserva catalogo de beneficios,
    parceiros, planos, sorteios, anuncios e o ESTOQUE de cupons (so limpa
    as atribuicoes).

    TRUNCATE (e nao DELETE) em ledger_events/apuracoes e proposital: essas
    tabelas tem trigger que bloqueia DELETE; TRUNCATE nao dispara trigger
    de linha e e a unica forma de zerar o ambiente de teste."""
    total = conn.execute(text("SELECT count(*) FROM wallet_accounts")).scalar()
    conn.execute(text("UPDATE beneficios_cupons SET account_id = NULL, atribuido_em = NULL"))
    conn.execute(
        text(
            """
            TRUNCATE consumo_lotes, numeros_sorte, capitalizacao_titulos,
                     compras_capitalizacao, nf_submissoes, notas_servico,
                     resgates, beneficios_usos, apuracao_contemplados,
                     apuracoes, assinaturas, lotes_creditos, ledger_events,
                     admin_usuarios_alteracoes
            """
        )
    )
    conn.execute(text("DELETE FROM wallet_accounts"))
    return total


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
