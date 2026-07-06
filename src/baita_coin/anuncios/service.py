"""Gestao de anuncios: CRUD administrativo + listagem publica dos vigentes
+ upload/entrega de imagens de banner."""
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine, Row

from baita_coin.anuncios import repository as repo
from baita_coin.anuncios.errors import (
    AnuncioNaoEncontrado,
    ImagemInvalida,
    ImagemNaoEncontrada,
)
from baita_coin.anuncios.schemas import (
    AnuncioResponse,
    AtualizarAnuncioRequest,
    CriarAnuncioRequest,
)
from baita_coin.config import settings

CONTENT_TYPES_PERMITIDOS = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
TAMANHO_MAXIMO_BYTES = 5 * 1024 * 1024  # 5MB por banner


def url_publica_da_imagem(imagem_id: UUID) -> str:
    return f"{settings.public_base_url}/v1/anuncios/imagens/{imagem_id}"


def salvar_imagem(engine: Engine, content_type: str, dados: bytes) -> dict:
    if content_type not in CONTENT_TYPES_PERMITIDOS:
        raise ImagemInvalida(
            "Formato de imagem nao suportado. Use JPEG, PNG, WebP ou GIF.",
            detalhes={"content_type_recebido": content_type},
        )
    if len(dados) == 0:
        raise ImagemInvalida("Arquivo de imagem vazio.")
    if len(dados) > TAMANHO_MAXIMO_BYTES:
        raise ImagemInvalida(
            "Imagem maior que o limite de 5MB.",
            detalhes={"tamanho_bytes": len(dados), "limite_bytes": TAMANHO_MAXIMO_BYTES},
        )

    imagem_id = uuid4()
    with engine.begin() as conn:
        repo.insert_imagem(conn, imagem_id, content_type, dados)
    return {"imagem_id": str(imagem_id), "imagem_url": url_publica_da_imagem(imagem_id)}


def obter_imagem(engine: Engine, imagem_id: UUID) -> Tuple[str, bytes]:
    with engine.begin() as conn:
        row = repo.get_imagem(conn, imagem_id)
        if row is None:
            raise ImagemNaoEncontrada(
                "imagem_id nao encontrado", detalhes={"imagem_id": str(imagem_id)}
            )
        return row.content_type, bytes(row.dados)


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
