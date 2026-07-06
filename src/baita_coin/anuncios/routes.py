from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.engine import Engine

from baita_coin.anuncios import service
from baita_coin.anuncios.schemas import (
    AnuncioResponse,
    AtualizarAnuncioRequest,
    CriarAnuncioRequest,
)
from baita_coin.db import engine as default_engine

router = APIRouter()


def get_engine() -> Engine:
    return default_engine


@router.get("/v1/anuncios", response_model=List[AnuncioResponse])
def listar_anuncios_endpoint(
    slot: Optional[str] = None, engine: Engine = Depends(get_engine)
) -> List[AnuncioResponse]:
    return service.listar_anuncios_ativos(engine, slot)


@router.get("/v1/anuncios/imagens/{imagem_id}")
def obter_imagem_endpoint(imagem_id: UUID, engine: Engine = Depends(get_engine)) -> Response:
    content_type, dados = service.obter_imagem(engine, imagem_id)
    # Imagens sao imutaveis (trocar o banner = novo upload, novo id), entao
    # cache agressivo e seguro e poupa o banco a cada render do app.
    return Response(
        content=dados,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@router.post("/v1/admin/anuncios/imagens", status_code=201)
async def upload_imagem_endpoint(
    arquivo: UploadFile = File(...), engine: Engine = Depends(get_engine)
) -> dict:
    dados = await arquivo.read()
    return service.salvar_imagem(engine, arquivo.content_type or "", dados)


@router.post("/v1/admin/anuncios", response_model=AnuncioResponse, status_code=201)
def criar_anuncio_endpoint(
    payload: CriarAnuncioRequest, engine: Engine = Depends(get_engine)
) -> AnuncioResponse:
    return service.criar_anuncio(engine, payload)


@router.get("/v1/admin/anuncios", response_model=List[AnuncioResponse])
def listar_anuncios_admin_endpoint(
    slot: Optional[str] = None, engine: Engine = Depends(get_engine)
) -> List[AnuncioResponse]:
    return service.listar_anuncios_admin(engine, slot)


@router.patch("/v1/admin/anuncios/{anuncio_id}", response_model=AnuncioResponse)
def atualizar_anuncio_endpoint(
    anuncio_id: UUID, payload: AtualizarAnuncioRequest, engine: Engine = Depends(get_engine)
) -> AnuncioResponse:
    return service.atualizar_anuncio(engine, anuncio_id, payload)
