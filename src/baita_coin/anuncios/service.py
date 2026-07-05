"""Gestao de anuncios: CRUD administrativo + listagem publica dos vigentes."""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine, Row

from baita_coin.anuncios import repository as repo
from baita_coin.anuncios.errors import AnuncioNaoEncontrado
from baita_coin.anuncios.schemas import AnuncioResponse, AtualizarAnuncioRequest, CriarAnuncioRequest


def _row_to_response(row: Row) -> AnuncioResponse:
    return AnuncioResponse(
        anuncio_id=row.anuncio_id,
        titulo=row.titulo,
        slot=row.slot,
        imagem_url=row.imagem_url,
        link_destino=row.link_destino,
        prioridade=row.prioridade,
        vigencia_inicio=row.vigencia_inicio,
        vigencia_fim=row.vigencia_fim,
        status=row.status,
    )


def criar_anuncio(engine: Engine, payload: CriarAnuncioRequest) -> AnuncioResponse:
    with engine.begin() as conn:
        row = repo.insert_anuncio(
            conn,
            uuid4(),
            payload.titulo,
            payload.slot,
            payload.imagem_url,
            payload.link_destino,
            payload.prioridade,
            payload.vigencia_inicio,
            payload.vigencia_fim,
        )
        return _row_to_response(row)


def listar_anuncios_ativos(engine: Engine, slot: Optional[str] = None) -> List[AnuncioResponse]:
    agora = datetime.now(timezone.utc)
    with engine.begin() as conn:
        rows = repo.list_anuncios_ativos(conn, agora, slot)
        return [_row_to_response(r) for r in rows]


def listar_anuncios_admin(engine: Engine, slot: Optional[str] = None) -> List[AnuncioResponse]:
    with engine.begin() as conn:
        rows = repo.list_anuncios_admin(conn, slot)
        return [_row_to_response(r) for r in rows]


def atualizar_anuncio(engine: Engine, anuncio_id: UUID, payload: AtualizarAnuncioRequest) -> AnuncioResponse:
    with engine.begin() as conn:
        existente = repo.get_anuncio(conn, anuncio_id)
        if existente is None:
            raise AnuncioNaoEncontrado(
                "anuncio_id nao encontrado", detalhes={"anuncio_id": str(anuncio_id)}
            )
        row = repo.atualizar_anuncio(
            conn,
            anuncio_id,
            payload.titulo,
            payload.slot,
            payload.imagem_url,
            payload.link_destino,
            payload.prioridade,
            payload.vigencia_inicio,
            payload.vigencia_fim,
            payload.status,
        )
        return _row_to_response(row)
