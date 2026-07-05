"""Acesso a dados dos anuncios -- so SQL, sem regra de negocio."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row


def insert_imagem(
    conn: Connection, imagem_id: UUID, content_type: str, dados: bytes
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO anuncios_imagens (imagem_id, content_type, dados, tamanho_bytes)
            VALUES (:imagem_id, :content_type, :dados, :tamanho_bytes)
            RETURNING imagem_id, content_type, tamanho_bytes, criado_em
            """
        ),
        {
            "imagem_id": str(imagem_id),
            "content_type": content_type,
            "dados": dados,
            "tamanho_bytes": len(dados),
        },
    ).first()


def get_imagem(conn: Connection, imagem_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM anuncios_imagens WHERE imagem_id = :id"), {"id": str(imagem_id)}
    ).first()


def insert_anuncio(
    conn: Connection,
    anuncio_id: UUID,
    titulo: str,
    slot: str,
    imagem_url: str,
    link_destino: Optional[str],
    prioridade: int,
    vigencia_inicio: Optional[datetime],
    vigencia_fim: Optional[datetime],
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO anuncios
                (anuncio_id, titulo, slot, imagem_url, link_destino, prioridade, vigencia_inicio, vigencia_fim)
            VALUES
                (:anuncio_id, :titulo, :slot, :imagem_url, :link_destino, :prioridade, :vigencia_inicio, :vigencia_fim)
            RETURNING *
            """
        ),
        {
            "anuncio_id": str(anuncio_id),
            "titulo": titulo,
            "slot": slot,
            "imagem_url": imagem_url,
            "link_destino": link_destino,
            "prioridade": prioridade,
            "vigencia_inicio": vigencia_inicio,
            "vigencia_fim": vigencia_fim,
        },
    ).first()


def get_anuncio(conn: Connection, anuncio_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM anuncios WHERE anuncio_id = :id"), {"id": str(anuncio_id)}
    ).first()


def list_anuncios_ativos(conn: Connection, momento: datetime, slot: Optional[str] = None) -> List[Row]:
    """Publico: so ativos e dentro da vigencia (vigencia nula = sempre valida)."""
    condicoes = [
        "status = 'ativo'",
        "(vigencia_inicio IS NULL OR vigencia_inicio <= :momento)",
        "(vigencia_fim IS NULL OR vigencia_fim > :momento)",
    ]
    params = {"momento": momento}
    if slot is not None:
        condicoes.append("slot = :slot")
        params["slot"] = slot
    where = " AND ".join(condicoes)
    return conn.execute(
        text(f"SELECT * FROM anuncios WHERE {where} ORDER BY prioridade DESC, criado_em DESC"), params
    ).all()


def list_anuncios_admin(conn: Connection, slot: Optional[str] = None) -> List[Row]:
    """Admin: todos, qualquer status/vigencia."""
    if slot is not None:
        return conn.execute(
            text("SELECT * FROM anuncios WHERE slot = :slot ORDER BY prioridade DESC, criado_em DESC"),
            {"slot": slot},
        ).all()
    return conn.execute(
        text("SELECT * FROM anuncios ORDER BY prioridade DESC, criado_em DESC")
    ).all()


def atualizar_anuncio(
    conn: Connection,
    anuncio_id: UUID,
    titulo: Optional[str],
    slot: Optional[str],
    imagem_url: Optional[str],
    link_destino: Optional[str],
    prioridade: Optional[int],
    vigencia_inicio: Optional[datetime],
    vigencia_fim: Optional[datetime],
    status: Optional[str],
) -> Row:
    return conn.execute(
        text(
            """
            UPDATE anuncios
            SET titulo = COALESCE(:titulo, titulo),
                slot = COALESCE(:slot, slot),
                imagem_url = COALESCE(:imagem_url, imagem_url),
                link_destino = COALESCE(:link_destino, link_destino),
                prioridade = COALESCE(:prioridade, prioridade),
                vigencia_inicio = COALESCE(:vigencia_inicio, vigencia_inicio),
                vigencia_fim = COALESCE(:vigencia_fim, vigencia_fim),
                status = COALESCE(:status, status)
            WHERE anuncio_id = :anuncio_id
            RETURNING *
            """
        ),
        {
            "anuncio_id": str(anuncio_id),
            "titulo": titulo,
            "slot": slot,
            "imagem_url": imagem_url,
            "link_destino": link_destino,
            "prioridade": prioridade,
            "vigencia_inicio": vigencia_inicio,
            "vigencia_fim": vigencia_fim,
            "status": status,
        },
    ).first()
