"""SQL do site-config. As duas linhas ('rascunho' e 'publicado') sao fixas,
criadas pela migration 0032 -- aqui so ha SELECT/UPDATE, nunca INSERT/DELETE
(exceto no historico de publicacoes, que e append-only)."""
import json
from typing import List
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row

VERSAO_RASCUNHO = "rascunho"
VERSAO_PUBLICADO = "publicado"


def get_versao(conn: Connection, versao: str) -> Row:
    return conn.execute(
        text("SELECT * FROM site_config WHERE versao = :versao"), {"versao": versao}
    ).first()


def salvar_rascunho(conn: Connection, conteudo: dict) -> Row:
    return conn.execute(
        text(
            """
            UPDATE site_config
            SET conteudo = CAST(:conteudo AS jsonb), atualizado_em = now()
            WHERE versao = 'rascunho'
            RETURNING *
            """
        ),
        {"conteudo": json.dumps(conteudo, ensure_ascii=False)},
    ).first()


def publicar_rascunho(conn: Connection) -> Row:
    return conn.execute(
        text(
            """
            UPDATE site_config AS publicado
            SET conteudo = rascunho.conteudo, atualizado_em = now(), publicado_em = now()
            FROM site_config AS rascunho
            WHERE publicado.versao = 'publicado' AND rascunho.versao = 'rascunho'
            RETURNING publicado.*
            """
        )
    ).first()


def copiar_publicado_para_rascunho(conn: Connection) -> Row:
    return conn.execute(
        text(
            """
            UPDATE site_config AS rascunho
            SET conteudo = publicado.conteudo, atualizado_em = now()
            FROM site_config AS publicado
            WHERE rascunho.versao = 'rascunho' AND publicado.versao = 'publicado'
            RETURNING rascunho.*
            """
        )
    ).first()


def insert_publicacao(conn: Connection, publicacao_id: UUID, conteudo: dict) -> None:
    conn.execute(
        text(
            """
            INSERT INTO site_config_publicacoes (publicacao_id, conteudo)
            VALUES (:publicacao_id, CAST(:conteudo AS jsonb))
            """
        ),
        {
            "publicacao_id": str(publicacao_id),
            "conteudo": json.dumps(conteudo, ensure_ascii=False),
        },
    )


def list_publicacoes(conn: Connection, limite: int) -> List[Row]:
    return conn.execute(
        text("SELECT * FROM site_config_publicacoes ORDER BY publicado_em DESC LIMIT :limite"),
        {"limite": limite},
    ).all()
